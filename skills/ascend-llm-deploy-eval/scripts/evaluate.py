"""Execute one case under container lock, with bounded independent attempts."""
import json
from pathlib import Path
import shutil
import subprocess
import time
from deploy import deploy
from finalize import release
from prepare_benchmark_tool import prepare
from stage_runtime import entry,read_plan,ready,save,service_identity,state,transition,update


def evaluate(root):
    s=read_plan(root); data=state(root)
    if data.get('case_status')=='PASSED':
        from validate_case import validate
        folder=Path(data['attempts'][-1]['folder'])
        validate(folder,json.loads((folder/'case.json').read_text()))
        return {'status':'PASSED','message':'Completed case revalidated; requests not replayed','artifacts':[str(folder/'validated.json')]}
    if data.get('case_status')=='RUNNING': raise ValueError('Interrupted case has unknown client state; finalize before recovery')
    if not ready(root,s): deploy(root)
    for name in ['case_runner.py','service_process.py','validate_case.py']:
        shutil.copy2(Path(__file__).with_name(name),root/'scripts'/name)
    limit=1+s['execution']['max_retries']
    for attempt in range(len(state(root)['attempts'])+1,limit+1):
        if not ready(root,s): raise ValueError('Service no longer READY; no blind case replay')
        folder=root/'results'/s['benchmark']['case']['id']/f'attempt-{attempt:02}'
        folder.mkdir(parents=True,exist_ok=False)
        prepare(Path(s['benchmark']['tool_dir']),folder/'tool')
        identity=service_identity(s,root)
        transition(root,'TESTING',case_status='RUNNING')
        data=state(root); item={'attempt':attempt,'folder':str(folder),'status':'RUNNING','stage':'evaluate'}
        data['attempts'].append(item); save(root/'run_state.json',data)
        with (folder/'runner.log').open('w') as log:
            result=subprocess.run(['docker','exec',data['container_id'],'python3',str(root/'scripts/case_runner.py'),str(root),str(folder)],stdout=log,stderr=subprocess.STDOUT)
        cleanup=json.loads((folder/'cleanup.json').read_text()) if (folder/'cleanup.json').exists() else {'released':False,'error':'No cleanup evidence'}
        summary=json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else {'status':'FAILED','error':'Runner failed; see runner.log'}
        passed=result.returncode==0 and summary['status']=='PASSED' and cleanup['released']
        item.update(status='PASSED' if passed else 'FAILED',returncode=result.returncode,summary=summary,cleanup=cleanup)
        data=state(root); data['attempts'][-1]=item; data['case_status']=item['status']; save(root/'run_state.json',data)
        try: unchanged=identity==service_identity(s,root)
        except Exception: unchanged=False
        transition(root,'READY' if unchanged else 'UNKNOWN')
        if passed:
            release(root,s['cleanup']['after_case'],'case')
            return {'status':'PASSED','message':f'Single case passed on attempt {attempt}; raw requests and prefix metrics verified','artifacts':[str(folder/'validated.json')]}
        if not cleanup['released'] or not unchanged:
            raise ValueError('Unsafe to retry: client cleanup or service identity not verified; finalize required')
        print(json.dumps({'event':'case_attempt_failed','attempt':attempt,'max_attempts':limit,'error':summary.get('error')}),flush=True)
        if attempt<limit: time.sleep(3)
    release(root,s['cleanup']['after_case'],'case')
    raise RuntimeError('Case exhausted retry budget; failure evidence retained; finalize task')

if __name__=='__main__': raise SystemExit(entry('evaluate',evaluate))
