"""Start one owned node; topology readiness and smoke belong to the coordinator."""
import json
from pathlib import Path
import shutil
import subprocess
from preflight import check
from stage_runtime import command,entry,inspect_owned,read_plan,ready,state,transition,ownership_digest,pool_state,save_pool


def start_node(root, action="start"):
    s=read_plan(root)
    if ready(root,s):
        return {'status':'PASSED','message':'READY identity verified; deploy and smoke skipped','artifacts':[]}
    check(root)
    data=state(root)
    if data['service'] not in ['ABSENT','RELEASED']: raise ValueError('Explicit cleanup required before redeploy')
    shared=pool_state(s) if s.get('container_registry') else {}
    if shared.get('active_run_dir') not in [None,'',str(root)]:
        raise ValueError('Previous deployment has not released the shared container')
    image=json.loads((root/'preflight-evidence.json').read_text())['image_id']
    existing=subprocess.run(['docker','inspect',s['target']['container']],capture_output=True,text=True)
    if existing.returncode==0:
        registered=shared.get('container_id') if s.get('container_registry') else data.get('container_id')
        c=inspect_owned(s,registered)
        if not registered or shared.get('removed') or c['Image']!=image: raise ValueError('Unregistered or changed container')
        if not c['State']['Running']:
            command(['docker','start',c['Id']])
            from stage_runtime import save
            save(root/'service-processes.json',[])
        cid=c['Id']
    else:
        args=['docker','run','-d','--name',s['target']['container'],'--label','benchmark.job_id='+s['job_id'],
              '--label','benchmark.spec_sha256='+ownership_digest(s),'--net=host','--shm-size='+s['container']['shm_size']]
        if s['container']['privileged']: args+=['--privileged']
        for d in s['container']['devices']: args+=['--device',d]
        for m in s['container']['mounts']: args+=['-v',m['source']+':'+m['target']+(':ro' if m['read_only'] else '')]
        args+=['-w',str(root),image,'sleep','infinity']
        cid=command(args,timeout=180).strip()
    if s.get('container_registry'):
        save_pool(s,container_id=cid,image_id=image,active_run_dir=str(root),removed=False)
    transition(root,'DEPLOYING',container_id=cid,image_id=image)
    shutil.copy2(Path(__file__).with_name('service_process.py'),root/'scripts/service_process.py')
    command(['docker','exec',cid,'python3',str(root/'scripts/service_process.py'),action,str(root)])
    return {'status':'PASSED','message':'Node processes started','artifacts':[]}


if __name__=='__main__': raise SystemExit(entry('deploy'))
