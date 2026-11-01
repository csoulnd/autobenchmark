"""Bind normalized task fields to this host before the serial loop starts."""
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
from stage_runtime import PACKAGE, command, digest, save
from task_runtime import read_task, resolved_task, storage_event

TOKEN = re.compile(r'\{\{([a-zA-Z_][a-zA-Z0-9_.]*)\}\}')


def lookup(context, name):
    value = context
    for key in name.split('.'):
        if not isinstance(value, dict) or key not in value:
            raise ValueError('Unresolved binding: '+name)
        value = value[key]
    return value


def expand(value, context, shell=False):
    if isinstance(value, dict):
        return {k: expand(v, context, shell) for k, v in value.items()}
    if isinstance(value, list):
        return [expand(v, context, shell) for v in value]
    if not isinstance(value, str):
        return value
    match = TOKEN.fullmatch(value)
    if match and not shell:
        return lookup(context, match[1])
    def replace(match):
        result = lookup(context, match[1])
        if isinstance(result, (dict, list)):
            raise ValueError('Structured binding must occupy entire value: '+match[1])
        return shlex.quote(str(result)) if shell else str(result)
    result = TOKEN.sub(replace, value)
    if '{{' in result or '}}' in result:
        raise ValueError('Unresolved or invalid template token')
    return result


def discover_network(preference=None):
    interfaces = json.loads(command(['ip', '-j', 'address', 'show']))
    choices = []
    for interface in interfaces:
        if interface.get('operstate') not in ['UP', 'UNKNOWN'] or interface['ifname'] == 'lo':
            continue
        if preference and interface['ifname'] != preference:
            continue
        for address in interface.get('addr_info', []):
            if address.get('family') == 'inet' and address.get('scope') == 'global':
                ipaddress.ip_address(address['local'])
                choices.append({'interface': interface['ifname'], 'ip': address['local']})
    if len(choices) != 1:
        raise ValueError('Select a verified network interface during attended preparation: '+str(choices))
    return choices[0]


def allocate_ports(requests):
    """Allocate disjoint ranges, holding sockets until all ranges are selected."""
    sockets, bases, all_ports = [], {}, []
    try:
        for name, width in requests.items():
            for attempt in range(100):
                first = socket.socket()
                first.bind(('0.0.0.0', 0))
                base = first.getsockname()[1]
                opened = [first]
                try:
                    if base + width > 65536:
                        raise OSError('Port range exceeds limit')
                    for port in range(base+1, base+width):
                        sock = socket.socket()
                        opened.append(sock)
                        sock.bind(('0.0.0.0', port))
                except OSError:
                    for sock in opened:
                        sock.close()
                    continue
                sockets.extend(opened)
                bases[name] = base
                all_ports.extend(range(base, base+width))
                break
            else:
                raise RuntimeError('Unable to allocate port range '+name)
        return bases, all_ports
    finally:
        for sock in sockets:
            sock.close()


def inspect_image_tools(image, job_id):
    name = job_id+'-000'
    existing = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
    if existing.returncode == 0:
        raise ValueError('Probe name already exists; do not reuse '+name)
    code = (PACKAGE/'scripts/discover_tool.py').read_text(encoding='utf-8-sig')
    try:
        output = command(['docker', 'run', '--rm', '--name', name,
            '--label', 'benchmark.job_id='+job_id, '--label', 'benchmark.role=preflight-probe',
            '--network=none', '--entrypoint', 'python3', image, '-c', code], timeout=120)
        return json.loads(output)
    finally:
        remaining = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True)
        if remaining.returncode == 0:
            container = json.loads(remaining.stdout)[0]
            labels = container['Config'].get('Labels') or {}
            if labels.get('benchmark.job_id') != job_id or labels.get('benchmark.role') != 'preflight-probe' or container['Image'] != image:
                raise ValueError('Probe ownership changed; refuse cleanup')
            command(['docker', 'rm', '-f', container['Id']])
            if subprocess.run(['docker', 'inspect', container['Id']], capture_output=True).returncode == 0:
                raise RuntimeError('Probe cleanup not verified')


def create_execution(spec, dep, root, index, bindings, network, port_bases, ports, tools, image):
    child = root/'services'/dep['id']
    for name in ['scripts', 'logs', 'results', 'configs']:
        (child/name).mkdir(parents=True, exist_ok=True)
    model_path = Path(bindings['model_paths'][dep['model']['id']])
    if not model_path.is_absolute() or not model_path.is_dir():
        raise ValueError('Missing model location for '+dep['model']['id'])
    model = {k: v for k, v in dep['model'].items() if k != 'id'}
    model['path'] = str(model_path.resolve())
    context = {'model': model, 'network': network, 'ports': port_bases,
               'paths': dict(bindings.get('paths', {})), 'run_dir': str(child), 'task_dir': str(root)}
    if '{{paths.proxy_program}}' in json.dumps(dep['commands']):
        proxy=child/'scripts/proxy.py'
        shutil.copy2(PACKAGE/'assets/dsv4-verified/load_balance_proxy_server_example.py',proxy)
        context['paths']['proxy_program']=str(proxy)
    commands = []
    for item in dep['commands']:
        argv = []
        for arg in item['argv']:
            argv.append(json.dumps(expand(arg['json'], context), ensure_ascii=False) if isinstance(arg, dict) else str(expand(arg, context)))
        env = expand(item.get('env', {}), context)
        if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k) for k in env):
            raise ValueError('Invalid environment variable name')
        bootstrap = expand(item.get('bootstrap', ''), context, shell=True)
        script = child/'scripts'/('start-'+item['name']+'.sh')
        script.write_text('#!/usr/bin/env bash\nset -e\n'+bootstrap+'\n'+
            ''.join('export '+k+'='+shlex.quote(str(v))+'\n' for k, v in env.items())+
            'exec '+shlex.join(argv)+'\n')
        commands.append({'name': item['name'], 'argv': ['bash', str(script)]})
    service = expand(dep['service'], context)
    service.update(commands=commands, npu_ids=dep['npu_ids'], ports=ports, network=network)
    if not all(isinstance(p, int) and p in ports for p in service['reset_ports']+[service['prefill_port']]):
        raise ValueError('Service ports must reference allocated ranges')
    for url in service['health_urls']+[service['endpoint']]+([service['gateway_health_url']] if service.get('gateway_health_url') else []):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname not in ['127.0.0.1', 'localhost'] or parsed.port not in ports:
            raise ValueError('Service URL must use allocated local port: '+url)
    mounts = list(bindings.get('mounts', []))
    for path, read_only in [(str(root), False), (str(model_path.resolve()), True)]:
        matching = [m for m in mounts if m['source'] == m['target'] and Path(path).is_relative_to(Path(m['source']))]
        if path == str(root) and any(m['read_only'] for m in matching):
            raise ValueError('Task workspace must be writable in container')
        if not matching:
            mounts.append({'source': path, 'target': path, 'read_only': read_only})
    if len({m['target'] for m in mounts}) != len(mounts):
        raise ValueError('Duplicate mount targets')
    devices = ['/dev/davinci'+str(i) for i in dep['npu_ids']]
    devices += [str(p) for p in map(Path, ['/dev/davinci_manager', '/dev/hisi_hdc', '/dev/ummu', '/dev/uburma']) if p.exists()]
    container = {**dep['container'], 'devices': devices, 'mounts': mounts}
    generated=list((child/'scripts').glob('start-*.sh'))
    if (child/'scripts/proxy.py').exists():
        generated.append(child/'scripts/proxy.py')
    fingerprints = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in generated}
    fingerprint = digest({'image': image, 'model': model, 'container': container,
                          'service': service, 'scripts': fingerprints})
    job_id = spec['job_id']+f'-{index:03}'
    first_case = next(c for c in spec['cases'] if c['deployment_id'] == dep['id'])
    execution = {'schema_version': 'resolved-1', 'job_id': job_id,
        'target': {'host': spec['target']['host'], 'container': job_id, 'work_dir': str(child), 'image': image},
        'model': model, 'container': container, 'deployment': {'service': service},
        'service_fingerprint': fingerprint,
        'benchmark': {'adapter': 'aisbench_prefix', 'tool_dir': str(PACKAGE/'assets/aisbench-prefix'),
                      'aisbench_work_path': tools['aisbench_work_path'], 'prefill_dp': dep['prefill_dp'], 'case': first_case},
        'execution': spec['execution'], 'cleanup': spec['cleanup']}
    save(child/'resolved.json', execution)
    save(child/'plan.json', {'execution_spec': execution, 'execution_sha256': digest(execution)})
    save(child/'scripts/service.json', service)
    return {'run_dir': str(child), 'execution_sha256': digest(execution),
            'service_fingerprint': fingerprint, 'scripts_sha256': fingerprints, 'tool_discovery': tools}


def prepare_task(root, bindings_path):
    root = root.resolve()
    spec = read_task(root)
    bindings = json.loads(Path(bindings_path).read_text(encoding='utf-8-sig'))
    if (root/'resolved-task.json').exists():
        _, previous = resolved_task(root)
        if previous['bindings_sha256'] != digest(bindings):
            raise ValueError('Bindings changed; use a new task directory')
        return {'status': 'PASSED', 'message': 'Existing preflight bindings verified; deploy rechecks live resources', 'artifacts': [str(root/'resolved-task.json')]}
    network = discover_network(bindings.get('network_interface'))
    ranges = {dep['id']+'.'+name: width for dep in spec['deployments'] for name, width in dep['ports'].items()}
    bases, ports = allocate_ports(ranges)
    resolved = {'plan_sha256': digest(spec), 'bindings_sha256': digest(bindings), 'run_dir': str(root), 'deployments': {}}
    tools_by_image = {}
    from preflight import check
    used = {c['deployment_id'] for c in spec['cases']}
    for index, dep in enumerate(spec['deployments'], 1):
        if dep['id'] not in used:
            raise ValueError('Deployment has no cases: '+dep['id'])
        image = json.loads(command(['docker', 'image', 'inspect', dep['image']]))[0]['Id']
        if image not in tools_by_image:
            tools_by_image[image] = inspect_image_tools(image, spec['job_id'])
        dep_bases = {name: bases[dep['id']+'.'+name] for name in dep['ports']}
        dep_ports = [port for name, width in dep['ports'].items() for port in range(dep_bases[name], dep_bases[name]+width)]
        item = create_execution(spec, dep, root, index, bindings, network, dep_bases, dep_ports, tools_by_image[image], image)
        check(Path(item['run_dir']))
        resolved['deployments'][dep['id']] = item
    save(root/'resolved-task.json', resolved)
    storage_event(root, 'bindings_resolved', task_id=spec['job_id'], bindings_sha256=resolved['bindings_sha256'])
    return {'status': 'PASSED', 'message': 'Attended preflight complete; runtime bindings frozen', 'artifacts': [str(root/'resolved-task.json')]}
