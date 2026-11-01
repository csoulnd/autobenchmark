"""Serial topology coordinator; node operations use owned local lifecycle scripts."""
import copy
import json
from pathlib import Path
import shlex
import re
import subprocess
import time
from stage_runtime import save, digest, http, command
from remote_node import RemoteNode
from topology import compile_deployment


def prepare_call(binding, request):
    if not re.fullmatch(r'(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9][A-Za-z0-9_.-]*',binding['host']):
        raise ValueError('Invalid SSH destination')
    if not Path(binding['package']).is_absolute():
        raise ValueError('Absolute node package path required')
    script = str(Path(binding['package'])/'scripts/node_prepare.py')
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', binding['host'],
        shlex.join(['python3', '-B', script])], input=json.dumps(request), capture_output=True, text=True, timeout=240)
    try:
        response = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise RuntimeError('Preparation transport failed: '+result.stderr[-2000:])
    if result.returncode or response['status'] != 'PASSED':
        raise RuntimeError('Node preparation failed: '+json.dumps(response))
    return response['result']


def container_pools(spec, bindings):
    """One compatible task container per host/runtime; union known mounts/devices."""
    pools, assignments, host_counts = {}, {}, {}
    for dep in spec['deployments']:
        for slot in sorted({i['placement']['node'] for i in dep['instances']}):
            binding=bindings['nodes'][slot]
            key=(binding['host'],digest({'runtime':dep['runtime'],'work_dir':binding['work_dir'],
                'mounts':binding.get('mounts',[])}))
            if key not in pools:
                number=host_counts.get(binding['host'],0)+1;host_counts[binding['host']]=number
                name=spec['job_id'] if number==1 else spec['job_id']+f'-{number:03}'
                pools[key]={'name':name,'job_id':spec['job_id'],'task_root':str(Path(binding['work_dir'])/spec['job_id']),
                    'devices':set(),'model_paths':set(),'plan_sha256':digest(spec)}
            pool=pools[key]
            pool['devices'].update(d for i in dep['instances'] if i['placement']['node']==slot for d in i['placement']['devices'])
            pool['model_paths'].add(binding['model_paths'][dep['model']['id']])
            assignments[(dep['id'],slot)]=pool
    for pool in pools.values():
        pool['devices']=sorted(pool['devices']);pool['model_paths']=sorted(pool['model_paths'])
    return assignments


def preflight(root, spec, bindings):
    pools=container_pools(spec,bindings)
    result = {'plan_sha256': digest(spec), 'bindings_sha256': digest(bindings), 'deployments': {}}
    for dep_index, dep in enumerate(spec['deployments'], 1):
        used = sorted({i['placement']['node'] for i in dep['instances']})
        nodes = {}
        for slot in used:
            binding = bindings['nodes'][slot]
            request_ports = {i['id']+'.'+p: width for i in dep['instances'] if i['placement']['node'] == slot
                             for p, width in i['ports'].items()}
            node_root = str(Path(binding['work_dir'])/spec['job_id']/dep['id'])
            discovered = prepare_call(binding, {'action': 'discover', 'run_dir': node_root,
                'job_id': spec['job_id']+f'-{dep_index:03}', 'image': dep['runtime']['image'],
                'bindings': binding, 'port_requests': request_ports})
            nodes[slot] = {**discovered, 'root': node_root, 'ports': {i['id']:
                {name: discovered['port_bases'][i['id']+'.'+name] for name in i['ports']}
                for i in dep['instances'] if i['placement']['node'] == slot}}
        compiled = compile_deployment(dep, nodes)
        registered = {'compiled': compiled, 'nodes': nodes, 'groups': {}}
        result['deployments'][dep['id']] = registered
        # Save discoveries before rendering so failures remain diagnosable.
        save(root/'preflight-progress.json', result)
        for group_index, (key, group) in enumerate(compiled['groups'].items(), 1):
            node, binding = nodes[group['node']], bindings['nodes'][group['node']]
            first_port = group['ports'][0]
            local_endpoint = group['health_urls'][0].rsplit('/', 1)[0]
            service = {'health_urls': group['health_urls'], 'model_health_urls':group['model_health_urls'], 'endpoint': local_endpoint,
                'reset_ports': [first_port], 'prefill_port': first_port}
            if key == compiled['endpoint_group']:
                service.update(endpoint=compiled['endpoint'], reset_urls=compiled['reset_urls'],
                               prefill_url=compiled['prefill_url'])
            max_length = min(i['launch']['args']['max-model-len'] for i in dep['instances'] if i['role'] != 'proxy')
            flat = {'id': dep['id']+'-'+key.replace('/', '-'), 'model': {**dep['model'], 'max_model_len': max_length},
                'container': dep['runtime']['container'], 'npu_ids': group['npu_ids'],
                'commands': group['commands'], 'service': service, 'prefill_dp': compiled['prefill_dp']}
            local_spec = {'job_id': spec['job_id']+f'-{dep_index:03}', 'target': {'host': binding['host']},
                          'execution': spec['execution'], 'cleanup': spec['cleanup'],
                          'container_pool':pools[(dep['id'],group['node'])]}
            reply = prepare_call({**binding,'package':node['package']}, {'action': 'render', 'run_dir': node['root'],
                'job_id': local_spec['job_id'], 'spec': local_spec, 'deployment': flat, 'index': group_index,
                'bindings': binding, 'ports': group['ports']})
            registered['groups'][key] = {**reply, 'host': binding['host'],
                'script': str(Path(node['package'])/'scripts/node_rpc.py')}
            save(root/'preflight-progress.json', result)
    save(root/'resolved-cluster.json', result)
    return {'status': 'PASSED', 'message': 'All topology nodes prepared', 'artifacts': [str(root/'resolved-cluster.json')]}


def clients(deployment):
    return {key: RemoteNode(item['host'], item['script'], item['run_dir'], item['job_id'], item['service_fingerprint'], item['scripts_sha256'])
            for key, item in deployment['groups'].items()}


def release_all(deployment, policy, scope):
    outcomes = {}
    for key, client in reversed(list(clients(deployment).items())):
        try:
            outcomes[key] = client.call('release', policy=policy, scope=scope)
        except Exception as exc:
            outcomes[key] = {'status': 'FAILED', 'error': repr(exc)}
    return outcomes


def deploy(root, spec, deployment):
    nodes = clients(deployment)
    state_path = root/'service-state.json'
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    if previous.get('status') == 'READY':
        responses = {key:node.call('identity') for key,node in nodes.items()}
        identities = {key:r['identity'] for key,r in responses.items()}
        if all(r.get('healthy',True) for r in responses.values()) and identities == previous['identities']:
            return
        raise ValueError('Registered service generation changed; finalize before retry')
    generations=[int(p.name.split('-')[-1]) for p in root.glob('deploy-*') if p.name.split('-')[-1].isdigit()]
    offset=max(generations,default=0)
    for attempt in range(1, spec['execution']['max_retries']+2):
        folder = root/f'deploy-{offset+attempt:02}'
        folder.mkdir(parents=True, exist_ok=True)
        try:
            for node in nodes.values():
                node.call('start')
            deadline = time.monotonic()+spec['execution']['startup_timeout_seconds']
            while True:
                responses = {key:node.call('identity',include_proxy=False) for key,node in nodes.items()}
                if all(r.get('healthy', True) for r in responses.values()):
                    identities = {key:r['identity'] for key,r in responses.items()}
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError('Topology startup deadline exceeded')
                time.sleep(5)
            nodes[deployment['compiled']['endpoint_group']].call('start_proxy')
            while True:
                responses={key:node.call('identity') for key,node in nodes.items()}
                if all(r.get('healthy',True) for r in responses.values()):
                    identities={key:r['identity'] for key,r in responses.items()}
                    break
                if time.monotonic()>=deadline:
                    raise TimeoutError('Proxy health deadline exceeded')
                time.sleep(2)
            request = {'model': spec['_served_name'], 'messages': [{'role':'user','content':'Reply with OK.'}],
                       'max_tokens':8, 'stream':False, 'temperature':0}
            save(folder/'smoke-request.json', request)
            endpoint = deployment['compiled']['endpoint']
            command(['curl','--noproxy','*','--silent','--show-error','--fail-with-body','--max-time',
                str(spec['execution']['smoke_timeout_seconds']),'-H','Content-Type: application/json',
                '--data-binary','@'+str(folder/'smoke-request.json'),'-o',str(folder/'smoke-response.json'),
                endpoint+'/v1/chat/completions'], timeout=spec['execution']['smoke_timeout_seconds']+10)
            response = json.loads((folder/'smoke-response.json').read_text())
            message = response.get('choices', [{}])[0].get('message', {})
            if response.get('error') or not any(message.get(k) for k in ['content','reasoning','reasoning_content']):
                raise ValueError('Smoke returned no generated content')
            for key, node in nodes.items():
                node.call('ready', identity=identities[key])
            save(state_path, {'status':'READY','identities':identities})
            return
        except Exception as exc:
            released = release_all(deployment, 'stop_container', 'failed_deployment')
            save(folder/'failure.json', {'error':repr(exc),'releases':released})
            if any(x['status'] != 'PASSED' for x in released.values()):
                raise RuntimeError('Node cleanup unverified; no retry') from exc
            if isinstance(exc,ValueError) or attempt == spec['execution']['max_retries']+1:
                raise


def finalize(root, spec, resolved):
    results = {key: release_all(dep, spec['cleanup']['task_end'], 'job') for key, dep in resolved['deployments'].items()}
    save(root/'release-results.json', results)
    failed = any(r['status'] != 'PASSED' for groups in results.values() for r in groups.values())
    return {'status':'FAILED' if failed else 'PASSED', 'message':'All registered node releases checked', 'artifacts':[str(root/'release-results.json')], 'releases':results}


def reconcile_failure(root, deployment, case_id):
    try:
        observations={key:node.call('assess_failure',case_id=case_id) for key,node in clients(deployment).items()}
    except Exception as exc:
        save(root/'service-state.json',{'status':'UNKNOWN','error':repr(exc)})
        return {'continue':False,'error':repr(exc)}
    states=[v['service'] for v in observations.values()]
    if not states or 'UNKNOWN' in states:
        save(root/'service-state.json',{'status':'UNKNOWN'})
        return {'continue':False,'nodes':observations}
    if all(v=='READY' for v in states):
        save(root/'service-state.json',{'status':'READY','identities':{k:v['identity'] for k,v in observations.items()}})
        return {'continue':True,'nodes':observations}
    releases=release_all(deployment,'stop_service','failed_sub_task')
    safe=all(v['status']=='PASSED' for v in releases.values())
    save(root/'service-state.json',{'status':'RELEASED' if safe else 'UNKNOWN'})
    return {'continue':safe,'nodes':observations,'releases':releases}


def run(root, spec, resolved):
    if (root/'summary.json').exists():
        summary=json.loads((root/'summary.json').read_text())
        summary['cleanup']=finalize(root,spec,resolved)
        if summary['cleanup']['status']!='PASSED':summary['status']='FAILED'
        save(root/'summary.json',summary)
        return summary
    progress=root/'task-state.json'
    results=json.loads(progress.read_text()) if progress.exists() else {}
    if any(v['status']=='RUNNING' for v in results.values()):
        raise ValueError('Interrupted topology task; finalize and inspect before a new run')
    try:
        for index, subtask in enumerate(spec['sub_tasks']):
            if subtask['id'] in results:
                continue
            results[subtask['id']]={'status':'RUNNING'}
            save(progress,results)
            dep_id = subtask['deployment_id']
            dep = resolved['deployments'][dep_id]
            definition = next(d for d in spec['deployments'] if d['id'] == dep_id)
            folder = root/'sub_tasks'/subtask['id']; folder.mkdir(parents=True, exist_ok=True)
            deployment_root = root/'services'/dep_id; deployment_root.mkdir(parents=True, exist_ok=True)
            # case ID in result artifacts identifies the execution, not the reusable load definition.
            case = copy.deepcopy(next(c for c in spec['cases'] if c['id'] == subtask['case_id']))
            case['id'] = subtask['id']
            failure_stage='deploy'
            try:
                deploy(deployment_root, {**spec,'_served_name':definition['model']['served_name']}, dep)
                from task_runtime import storage_event
                storage_event(root,'deployment_verified',deployment_id=dep_id)
                client = clients(dep)[dep['compiled']['endpoint_group']]
                before={key:node.call('identity')['identity'] for key,node in clients(dep).items()}
                failure_stage='evaluate'
                result = client.call('evaluate', timeout=(case['timeout_seconds']+120)*(spec['execution']['max_retries']+1), case=case)
                after={key:node.call('identity')['identity'] for key,node in clients(dep).items()}
                if before!=after:
                    raise RuntimeError('A topology service changed during evaluation')
                results[subtask['id']] = result
            except Exception as exc:
                recovery=reconcile_failure(deployment_root,dep,subtask['id'])
                results[subtask['id']] = {'status':'FAILED','error':repr(exc),'failure_stage':failure_stage,
                    'on_failure':subtask['on_failure'],'phase_id':subtask['phase_id'],'reconciliation':recovery}
                if not recovery['continue']:
                    results[subtask['id']]['blocked']=True
                    break
            finally:
                save(folder/'result.json', results[subtask['id']])
                save(progress,results)
                from task_runtime import storage_event
                storage_event(root,'case_finished',sub_task_id=subtask['id'],case_id=subtask['case_id'],deployment_id=dep_id,status=results[subtask['id']]['status'])
            next_dep = spec['sub_tasks'][index+1]['deployment_id'] if index+1 < len(spec['sub_tasks']) else None
            policy = subtask['after_case']
            if next_dep and next_dep != dep_id and policy=='keep_service':
                policy='stop_service'
            releases = release_all(dep, policy, 'sub_task:'+subtask['id'])
            save(folder/'release.json', releases)
            if any(r['status'] != 'PASSED' for r in releases.values()):
                results[subtask['id']]['release_failed'] = True
                save(folder/'result.json',results[subtask['id']])
                save(progress,results)
                break
            if policy != 'keep_service':
                save(deployment_root/'service-state.json', {'status':'RELEASED'})
    finally:
        cleanup = finalize(root, spec, resolved)
        for subtask in spec['sub_tasks']:
            results.setdefault(subtask['id'], {'status':'NOT_RUN'})
        passed = cleanup['status']=='PASSED' and all(v['status']=='PASSED' and not v.get('release_failed') for v in results.values())
        summary = {'status':'PASSED' if passed else 'FAILED','message':'Serial topology task finished; inspect per-node evidence','artifacts':[str(root/'summary.json')],'sub_tasks':results,'cleanup':cleanup}
        save(root/'summary.json', summary)
    return summary
