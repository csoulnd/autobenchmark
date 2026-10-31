"""Plan one case. Fill defaults, validate inputs, and snapshot selected recipe."""
import argparse
import copy
import json
from pathlib import Path, PurePosixPath
import shutil
from stage_runtime import PACKAGE, digest, recipe, save


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
    return s


def validate(spec):
    from jsonschema import Draft202012Validator
    errors=[f'{e.json_path}: {e.message}' for e in Draft202012Validator(load_json(PACKAGE/'schemas/job_spec.schema.json')).iter_errors(spec)]
    if errors: return errors
    s=spec; c=s['benchmark']['case']
    if s['target']['container']!=s['job_id']: errors.append('Container must equal job_id')
    root=PurePosixPath(s['target']['work_dir'])
    if root.name!=s['job_id'] or '..' in root.parts: errors.append('work_dir must end with job_id and contain no traversal')
    mounts=s['container']['mounts']
    for path in [s['target']['work_dir'],s['model']['path']]:
        if not any(m['source']==m['target'] and PurePosixPath(path).is_relative_to(PurePosixPath(m['source'])) for m in mounts):
            errors.append('Required same-path mount absent: '+path)
    if c['input_tokens']+c['output_tokens']>s['model']['max_model_len']: errors.append('Context limit exceeded')
    if c['formal_requests']<c['concurrency']: errors.append('Requests cannot reach requested concurrency')
    if s['state']=='ready' and s['unresolved']: errors.append('Ready spec contains unresolved items')
    try: recipe(s).validate(s)
    except Exception as exc: errors.append('Recipe: '+str(exc))
    return errors


def plan(spec,root):
    s=normalize(spec); errors=validate(s)
    if errors: raise ValueError('; '.join(errors))
    if s['state']!='ready': raise ValueError('Draft requires attended resolution')
    result={'job_spec':s,'job_spec_sha256':digest(s),'status':'PLANNED','runtime_verified':False}
    if (root/'plan.json').exists() and load_json(root/'plan.json')!=result:
        raise ValueError('Existing plan differs; use a new job_id')
    root.mkdir(parents=True,exist_ok=True)
    for name in ['configs','scripts','logs','results']:(root/name).mkdir(exist_ok=True)
    save(root/'plan.json',result); save(root/'job_spec.json',s)
    # Preserve the complete executable package used by this job.
    if not (root/'skill-snapshot').exists():
        shutil.copytree(PACKAGE,root/'skill-snapshot',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    return result


def main():
    p=argparse.ArgumentParser(); p.add_argument('--run-dir',type=Path,required=True); p.add_argument('--job-spec',type=Path)
    a=p.parse_args()
    try:
        if not a.run_dir.is_absolute() or a.job_spec is None: raise ValueError('Absolute run-dir and --job-spec required')
        plan(load_json(a.job_spec),a.run_dir)
        print(json.dumps({'stage':'plan_run','status':'PLANNED','message':'Single-case plan saved; defaults recorded','artifacts':[str(a.run_dir/'plan.json')]}))
        return 0
    except Exception as exc:
        print(json.dumps({'stage':'plan_run','status':'BLOCKED','message':str(exc),'artifacts':[]})); return 2

if __name__=='__main__': raise SystemExit(main())
