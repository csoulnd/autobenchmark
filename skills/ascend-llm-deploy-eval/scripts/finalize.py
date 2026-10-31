"""Explicit, idempotent policy release; keep shared images/weights and evidence."""
import json
import re
import time
from stage_runtime import command,entry,inspect_owned,read_plan,save,state,transition,update


def release(root,policy,scope):
    s=read_plan(root); data=state(root); evidence={'scope':scope,'policy':policy,'status':'kept' if policy=='keep_service' else 'released'}
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
        transition(root,'RELEASED',smoke_identity=None)
    data=state(root); data['releases'].append(evidence); save(root/'run_state.json',data)
    return evidence


def finalize(root):
    s=read_plan(root)
    try: released=release(root,s['cleanup']['task_end'],'job')
    except Exception as exc:
        data=state(root); data['releases'].append({'scope':'job','status':'release_failed','error':repr(exc)})
        save(root/'run_state.json',data); raise
    data=state(root)
    result={'job_id':s['job_id'],'case':s['benchmark']['case'],'evaluation_status':data.get('case_status','NOT_RUN'),
        'attempts':data['attempts'],'release':released,'service_state':data['service'],
        'shared_images_and_weights_retained':True,'container_retained':True}
    stages=root/'logs/stages.jsonl'
    result['stage_failures']=[r for r in map(json.loads,stages.read_text().splitlines()) if r['status']=='FAILED'] if stages.exists() else []
    save(root/'summary.json',result)
    return {'status':'PASSED','message':'Cleanup policy applied and verified; evaluation status recorded separately','artifacts':[str(root/'summary.json')]}

if __name__=='__main__': raise SystemExit(entry('finalize',finalize))
