"""Freeze a serial task, fill defaults, and snapshot execution code."""
import argparse
import copy
import json
from pathlib import Path
import shutil
from stage_runtime import PACKAGE, digest, save


def load_json(path):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValueError('Duplicate JSON key: '+key)
            result[key]=value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),object_pairs_hook=pairs)


def normalize(spec):
    s=copy.deepcopy(spec)
    e=s.setdefault('execution',{})
    for k,v in {'smoke':'default','max_retries':3,'startup_timeout_seconds':1800,'smoke_timeout_seconds':240}.items():
        e.setdefault(k,v)
    if s.get('schema_version')=='3.0':
        s.setdefault('cleanup',{'after_case':'keep_service','task_end':'stop_container'})
        for case in s.get('cases',[]):
            for k,v in {'formal_requests':case['concurrency']*4,'prefix_num':1,'seed':1,
                        'request_rate':0,'warmup':True,'reset_cache':True,'timeout_seconds':5400}.items():
                case.setdefault(k,v)
    for subtask in s.get('sub_tasks', []):
        subtask.setdefault('after_case', s['cleanup']['after_case'])
    return s


def validate(spec):
    from jsonschema import Draft202012Validator
    errors=[f'{e.json_path}: {e.message}' for e in Draft202012Validator(load_json(PACKAGE/'schemas/job_spec.schema.json')).iter_errors(spec)]
    if errors: return errors
    from task_runtime import validate_task
    return validate_task(spec)



def plan(spec,root):
    s=normalize(spec); errors=validate(s)
    if errors: raise ValueError('; '.join(errors))
    if s['state']!='ready': raise ValueError('Draft requires attended resolution')
    result={'job_spec':s,'job_spec_sha256':digest(s),'status':'PLANNED','runtime_verified':False}
    if s['schema_version']=='3.0':
        result['sequence']=s['sub_tasks']
    if (root/'plan.json').exists() and load_json(root/'plan.json')!=result:
        raise ValueError('Existing plan differs; use a new job_id')
    root.mkdir(parents=True,exist_ok=True)
    for name in ['configs','scripts','logs','results']:(root/name).mkdir(exist_ok=True)
    save(root/'plan.json',result); save(root/'job_spec.json',s)
    # Preserve the complete executable package used by this job.
    if not (root/'skill-snapshot').exists():
        shutil.copytree(PACKAGE,root/'skill-snapshot',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    if s['schema_version']=='3.0':
        # Relative snapshot entry makes the generated task package transferable.
        (root/'run.sh').write_text('#!/usr/bin/env bash\nset -euo pipefail\n'
            'RUN_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"\n'
            'exec python3 "$RUN_DIR/skill-snapshot/scripts/run_task.py" --run-dir "$RUN_DIR" "$@"\n',encoding='utf-8',newline='\n')
        from task_runtime import storage_event
        storage_event(root,'task_normalized',task_id=s['job_id'],plan_sha256=result['job_spec_sha256'])
    return result


def main():
    p=argparse.ArgumentParser(); p.add_argument('--run-dir',type=Path,required=True); p.add_argument('--job-spec',type=Path)
    a=p.parse_args()
    try:
        if not a.run_dir.is_absolute() or a.job_spec is None: raise ValueError('Absolute run-dir and --job-spec required')
        plan(load_json(a.job_spec),a.run_dir)
        print(json.dumps({'stage':'plan_run','status':'PLANNED','message':'Plan saved; defaults and execution order recorded','artifacts':[str(a.run_dir/'plan.json')]}))
        return 0
    except Exception as exc:
        print(json.dumps({'stage':'plan_run','status':'BLOCKED','message':str(exc),'artifacts':[]})); return 2

if __name__=='__main__': raise SystemExit(main())
