"""Attended node preparation. Reads a data request; writes only its task directory."""
import json
from pathlib import Path
import re
import sys
import shutil
from stage_runtime import save, command, PACKAGE, digest
from task_preflight import discover_network, allocate_ports, inspect_image_tools, create_execution


def prepare(request):
    root = Path(request['run_dir'])
    job_id = request['job_id']
    if not root.is_absolute() or '..' in root.parts or not re.fullmatch(r'\d{8}-\d{3}(?:-\d{3})*', job_id):
        raise ValueError('Invalid task root or job ID')
    marker = root/'node-owner.json'
    if marker.exists():
        if json.loads(marker.read_text()) != {'job_id': job_id}:
            raise ValueError('Node directory belongs to another task')
    elif root.exists() and any(root.iterdir()):
        raise ValueError('Unregistered nonempty node directory')
    root.mkdir(parents=True, exist_ok=True)
    save(marker, {'job_id': job_id})
    if request['action'] == 'discover':
        saved=root/'discovery.json'
        if saved.exists() and list(root.glob('render-*.json')):
            previous=json.loads(saved.read_text())
            if previous.get('request_sha256')!=digest(request):
                raise ValueError('Frozen discovery request changed')
            return previous
        snapshot=root/'skill-snapshot'
        if not snapshot.exists():
            shutil.copytree(PACKAGE,snapshot,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        network = discover_network(request['bindings'].get('network_interface'))
        bases, _ = allocate_ports(request['port_requests'])
        image = json.loads(command(['docker', 'image', 'inspect', request['image']]))[0]['Id']
        tools = inspect_image_tools(image, job_id)
        result = {'request_sha256':digest(request),'network': network, 'port_bases': bases, 'image': image, 'tools': tools,
                  'package': str(snapshot), 'npu_snapshot': command(['npu-smi', 'info']),
                  'script_hashes': {p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in (PACKAGE/'scripts').glob('*.py')}}
        save(root/'discovery.json', result)
        return result
    if request['action'] == 'render':
        discovery = json.loads((root/'discovery.json').read_text())
        dep = request['deployment']
        # The coordinator sends compiled commands, but never receives authority to
        # replace an existing frozen execution artifact with a different definition.
        signature = digest(request)
        frozen = root/('render-'+dep['id']+'.json')
        if frozen.exists():
            previous = json.loads(frozen.read_text())
            if previous['request_sha256'] != signature:
                raise ValueError('Frozen node render request changed')
            return previous['result']
        result = create_execution(request['spec'], dep, root, request['index'], request['bindings'],
            discovery['network'], {}, request['ports'], discovery['tools'], discovery['image'])
        from preflight import check
        check(Path(result['run_dir']))
        result['job_id'] = json.loads((Path(result['run_dir'])/'resolved.json').read_text())['job_id']
        save(frozen, {'request_sha256': signature, 'result': result})
        return result
    raise ValueError('Unknown preparation action')


if __name__ == '__main__':
    try:
        result = {'status': 'PASSED', 'result': prepare(json.load(sys.stdin))}
    except Exception as exc:
        result = {'status': 'FAILED', 'error': repr(exc)}
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result['status'] == 'PASSED' else 2)
