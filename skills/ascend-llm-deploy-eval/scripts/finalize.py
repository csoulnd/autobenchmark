"""Explicit, idempotent policy release; keep shared images/weights and evidence."""
import json
import re
import time
from pathlib import Path
from stage_runtime import command,entry,inspect_owned,read_plan,save,state,transition,update,pool_state,save_pool


def release(root,policy,scope):
    s=read_plan(root)
    shared=pool_state(s) if s.get('container_registry') else {}
    if scope=='job' and shared.get('active_run_dir') and shared['active_run_dir']!=str(root):
        return release(Path(shared['active_run_dir']),policy,scope)
    if s.get('container_registry'):
        if shared.get('removed') or not shared.get('container_id'):
            return {'scope':scope,'policy':policy,'status':'released','verification':'Task container absent or already removed'}
        if scope!='job' and shared.get('active_run_dir') not in [None,'',str(root)]:
            raise ValueError('Shared container belongs to another active deployment')
        update(root,container_id=shared['container_id'],image_id=shared['image_id'])
    data=state(root); evidence={'scope':scope,'policy':policy,'status':'kept' if policy=='keep_service' else 'released'}
    if policy=='keep_service':
        pass
    elif not data.get('container_id'):
        evidence['verification']='No container created by this job'
    else:
        c=inspect_owned(s,data['container_id'])
        if c['Image']!=data['image_id']: raise ValueError('Registered image changed')
        if policy=='stop_service' and c['State']['Running']:
            evidence['processes']=json.loads(command(['docker','exec',c['Id'],'python3',str(root/'scripts/service_process.py'),'stop',str(root)],timeout=180))
        elif policy=='stop_container':
            if c['State']['Running']:
                (root/'logs/processes-before-finalize.txt').write_text(command(['docker','top',c['Id'],'-eo','pid,lstart,args']))
                command(['docker','stop','-t','30',c['Id']],timeout=180)
            current=inspect_owned(s,c['Id'])['State']
            evidence['container_state']=current
            if current['Running'] or current['Pid']!=0: raise RuntimeError('Container stop verification failed')
            snapshot=root/'logs/processes-before-finalize.txt'
            known=set(re.findall(r'^\s*(\d+)\s',snapshot.read_text(),re.M)) if snapshot.exists() else set()
            for attempt in range(4):
                npu=command(['npu-smi','info'])
                active=set(re.findall(r'^\|\s*\d+\s*\|\s*(\d+)\s*\|',npu,re.M))
                if not known.intersection(active): break
                if attempt==3: raise RuntimeError('Owned NPU process remains after container stop')
                time.sleep(3)
            (root/'logs/npu-after-finalize.txt').write_text(npu)
            sockets=command(['ss','-lntp'])
            (root/'logs/ports-after-finalize.txt').write_text(sockets)
            if known.intersection(re.findall(r'pid=(\d+)',sockets)):
                raise RuntimeError('Owned process still has listening socket')
            evidence['owned_npu_processes_remaining']=[]
            evidence['owned_listeners_remaining']=[]
            processes=root/'service-processes.json'
            if processes.exists():
                evidence['stopped_processes']=json.loads(processes.read_text())
                save(processes,[])
        if policy=='stop_service' and not c['State']['Running']:
            save(root/'service-processes.json',[])
        if s.get('container_registry'):
            save_pool(s,active_run_dir='')
            if scope=='job' and policy=='stop_container':
                command(['docker','rm',c['Id']])
                if command(['docker','ps','-aq','--filter','id='+c['Id']]).strip():
                    raise RuntimeError('Task container removal not verified')
                save_pool(s,removed=True)
                evidence['container_removed']=True
        transition(root,'RELEASED',smoke_identity=None)
    data=state(root); data['releases'].append(evidence); save(root/'run_state.json',data)
    return evidence


if __name__=='__main__': raise SystemExit(entry('finalize'))
