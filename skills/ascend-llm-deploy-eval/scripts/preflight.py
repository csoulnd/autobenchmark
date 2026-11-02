"""Verify user-selected resources and prepared inputs without mutating services."""
import json
from pathlib import Path
import re
import socket
from stage_runtime import command, entry, read_plan, ready, save, state


def _check(root, report):
    s=read_plan(root)
    def stage(name):
        if report['current'] and report['checks'][report['current']]=='RUNNING': report['checks'][report['current']]='PASSED'
        report['current']=name
        report['checks'][name]='RUNNING'
    stage('storage')
    service=s['deployment']['service']
    if s.get('storage'):
        from disk_guard import check as disk_check
        report['storage']=disk_check(s['storage']['root'], s['storage']['subtasks'], admission=True)
    else:
        report['checks']['storage']='NOT_APPLICABLE'
    save(root/'scripts/service.json',service)
    stage('image')
    evidence={'image_id':json.loads(command(['docker','image','inspect',s['target']['image']]))[0]['Id']}
    save(root/'preflight-evidence.json',evidence)
    stage('mounts')
    for mount in s['container']['mounts']:
        if not Path(mount['source']).exists(): raise ValueError('Missing mount: '+mount['source'])
    stage('devices')
    for device in s['container']['devices']:
        if not Path(device).exists(): raise ValueError('Missing device: '+device)
    stage('weights')
    model=Path(s['model']['path'])
    if not model.is_dir(): raise ValueError('Missing model directory')
    index=model/'model.safetensors.index.json'
    if index.exists():
        shards=set(json.loads(index.read_text())['weight_map'].values())
        for name in shards:
            path=(model/name).resolve()
            if not path.is_relative_to(model.resolve()) or not path.is_file(): raise ValueError('Missing weight shard: '+name)
        evidence['weight_shards']=len(shards)
    stage('tokenizer')
    for name in ['tokenizer.json','tokenizer_config.json']:
        if not (model/name).is_file(): raise ValueError('Missing '+name)
    stage('benchmark_tool')
    if not (Path(s['benchmark']['tool_dir'])/'aisbench_test.py').is_file(): raise ValueError('Missing benchmark tool')
    stage('network')
    network=service.get('network')
    if network:
        from task_preflight import network_addresses
        addresses=network_addresses('dev',network['interface'])
        if not any(x.get('local')==network['ip'] for i in addresses for x in i.get('addr_info',[])):
            raise ValueError('Configured network address absent')
        evidence['network']=addresses
    else:
        report['checks']['network']='NOT_APPLICABLE'
    stage('resource_or_reuse')
    if ready(root,s):
        evidence['reuse']='READY instance verified'
    else:
        if state(root)['service'] not in ['ABSENT','RELEASED']:
            raise ValueError('Existing service not READY; inspect/finalize before deployment')
        npu=command(['npu-smi','info']); evidence['npu']=npu
        free={int(x) for x in re.findall(r'No running processes found in NPU (\d+)',npu)}
        if not set(service['npu_ids'])<=free:
            save(root/'preflight-evidence.json',evidence)
            raise ValueError('Requested NPUs occupied or state unknown; do not touch other jobs')
        for port in service['ports']:
            try:
                with socket.socket() as sock: sock.bind(('0.0.0.0',port))
            except OSError as exc:
                raise RuntimeError(f'Port preflight failed: address=0.0.0.0 port={port} errno={exc.errno}; inspect ss and ownership before retry') from exc
        evidence['free_ports']=service['ports']
    report['checks'][report['current']]='PASSED'
    report['current']=None
    save(root/'preflight-evidence.json',evidence)
    return {'status':'PASSED','message':'Selected dependencies and service/resources verified','artifacts':[str(root/'preflight-evidence.json')]}

def check(root):
    from datetime import datetime, timezone
    report={'time':datetime.now(timezone.utc).isoformat(), 'current':None,
            'checks':{name:'NOT_RUN' for name in ('storage','image','mounts','devices','weights','tokenizer','benchmark_tool','network','resource_or_reuse')}}
    try:
        result=_check(root, report)
        report['status']='PASSED'
        return result
    except Exception as exc:
        report['status']='FAILED'; report['error']=repr(exc)
        if report['current']: report['checks'][report['current']]='FAILED'
        raise
    finally:
        try: save(root/'preflight-report.json',report)
        except OSError: pass


if __name__=='__main__': raise SystemExit(entry('preflight'))
