"""Start the selected recipe; default smoke is one real curl inference."""
import json
from pathlib import Path
import shutil
import subprocess
import time
from preflight import check
from stage_runtime import command,digest,entry,http,inspect_owned,read_plan,ready,save,service_identity,state,transition,update


def deploy_once(root):
    s=read_plan(root)
    if ready(root,s):
        return {'status':'PASSED','message':'READY identity verified; deploy and smoke skipped','artifacts':[]}
    check(root)
    data=state(root)
    if data['service'] not in ['ABSENT','RELEASED']: raise ValueError('Explicit cleanup required before redeploy')
    image=json.loads((root/'preflight-evidence.json').read_text())['image_id']
    existing=subprocess.run(['docker','inspect',s['target']['container']],capture_output=True,text=True)
    if existing.returncode==0:
        c=inspect_owned(s,data.get('container_id'))
        if not data.get('container_id') or c['Image']!=image: raise ValueError('Unregistered or changed container')
        if not c['State']['Running']: command(['docker','start',c['Id']])
        cid=c['Id']
    else:
        args=['docker','run','-d','--name',s['target']['container'],'--label','benchmark.job_id='+s['job_id'],
              '--label','benchmark.spec_sha256='+digest(s),'--net=host','--shm-size='+s['container']['shm_size']]
        if s['container']['privileged']: args+=['--privileged']
        for d in s['container']['devices']: args+=['--device',d]
        for m in s['container']['mounts']: args+=['-v',m['source']+':'+m['target']+(':ro' if m['read_only'] else '')]
        args+=['-w',str(root),image,'sleep','infinity']
        cid=command(args,timeout=180).strip()
    transition(root,'DEPLOYING',container_id=cid,image_id=image)
    shutil.copy2(Path(__file__).with_name('service_process.py'),root/'scripts/service_process.py')
    command(['docker','exec',cid,'python3',str(root/'scripts/service_process.py'),'start',str(root)])
    service=json.loads((root/'scripts/service.json').read_text())
    deadline=time.monotonic()+s['execution']['startup_timeout_seconds']
    while True:
        try:
            service_identity(s,root)
            for url in service['health_urls']: http(url)
            http(service['endpoint']+'/healthcheck')
            break
        except Exception:
            if time.monotonic()>=deadline:
                transition(root,'FAILED',reason='Startup deadline exceeded')
                raise TimeoutError('Startup deadline exceeded; finalize required')
            time.sleep(5)
    transition(root,'DEPLOYED')
    request={'model':s['model']['served_name'],'messages':[{'role':'user','content':'Reply with OK.'}],
             'max_tokens':8,'stream':False,'temperature':0}
    save(root/'results/smoke-request.json',request)
    response=root/'results/smoke-response.json'
    args=['curl','--noproxy','*','--silent','--show-error','--fail-with-body',
          '--max-time',str(s['execution']['smoke_timeout_seconds']),'-H','Content-Type: application/json',
          '--data-binary','@'+str(root/'results/smoke-request.json'),'-o',str(response),service['endpoint']+'/v1/chat/completions']
    save(root/'results/smoke-command.json',args)
    try:
        command(args,timeout=s['execution']['smoke_timeout_seconds']+10)
        result=json.loads(response.read_text()); choices=result.get('choices',[])
        if result.get('error') or not choices: raise RuntimeError('Smoke returned API error/no choices')
        message=choices[0].get('message',{})
        if not (message.get('content') or message.get('reasoning_content') or message.get('reasoning')):
            raise RuntimeError('Smoke produced no generated content')
        identity=service_identity(s,root)
        save(root/'results/smoke-result.json',{'status':'PASSED','strategy':'default','identity':identity})
        transition(root,'READY',smoke_identity=identity)
    except Exception as exc:
        transition(root,'FAILED',reason=str(exc)); raise
    version_code="import importlib.metadata as m,json,platform; print(json.dumps({'python':platform.python_version(),'packages':{n:m.version(n) for n in ['vllm','vllm-ascend','ais_bench_benchmark','torch','torch-npu']}}))"
    (root/'results/versions.json').write_text(command(['docker','exec',cid,'python3','-c',version_code]))
    return {'status':'PASSED','message':'Service READY; one default curl inference passed','artifacts':[str(root/'results/smoke-result.json')]}


def deploy(root):
    s=read_plan(root)
    if ready(root,s):
        return {'status':'PASSED','message':'READY identity verified; deploy and smoke skipped','artifacts':[]}
    # Only bounded operational retries; invalid input/ownership is never replayed.
    limit=1+s['execution']['max_retries']
    attempts=state(root).get('deploy_attempts',[])
    for number in range(len(attempts)+1,limit+1):
        attempt={'attempt':number,'status':'RUNNING'}
        attempts.append(attempt); update(root,deploy_attempts=attempts)
        try:
            result=deploy_once(root)
            attempt['status']='PASSED'; update(root,deploy_attempts=attempts)
            return result
        except (RuntimeError,TimeoutError,subprocess.TimeoutExpired) as exc:
            attempt.update(status='FAILED',error=repr(exc)); update(root,deploy_attempts=attempts)
            evidence=root/'results'/f'deploy-attempt-{number:02}'
            evidence.mkdir(exist_ok=True)
            for directory in ['logs','results']:
                for path in (root/directory).glob('*'):
                    if path.is_file(): shutil.copy2(path,evidence/path.name)
            from finalize import release
            release(root,'stop_container','failed_deployment')
            print(json.dumps({'event':'deploy_attempt_failed','attempt':number,'max_attempts':limit,'error':repr(exc)}),flush=True)
            if number<limit: time.sleep(3)
        except Exception as exc:
            attempt.update(status='FAILED',error=repr(exc),retry_blocked=True)
            update(root,deploy_attempts=attempts)
            raise
    raise RuntimeError('Deployment exhausted retry budget; inspect attempt evidence')

if __name__=='__main__': raise SystemExit(entry('deploy',deploy))
