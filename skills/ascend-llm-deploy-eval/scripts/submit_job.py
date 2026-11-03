"""Build a frozen job locally and upload once per physical destination."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tarfile
from plan_run import check_dependencies, load_json, normalize, validate, candidate_ids, plan
from stage_runtime import PACKAGE


def ssh(host, argv):
    if not re.fullmatch(r'(?:[\w.-]+@)?[\w.-]+',host): raise ValueError('Invalid host')
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',host,
        shlex.join([str(x) for x in argv])],capture_output=True,text=True)
    if result.returncode: raise RuntimeError(result.stdout+'\n'+result.stderr)
    return result.stdout


def remote_path(value):
    p=PurePosixPath(value)
    if not p.is_absolute() or '..' in p.parts: raise ValueError('Absolute remote path required')
    return p


def build(spec_path, bindings_path, jobs_dir, date, host, remote_root):
    check_dependencies()
    spec=load_json(spec_path);bindings=load_json(bindings_path)
    jobs_dir=Path(jobs_dir).resolve();jobs_dir.mkdir(parents=True,exist_ok=True)
    if 'job_id' in spec: raise ValueError('Job ID is allocated by the packager')
    for job_id in candidate_ids(date):
        spec['job_id']=job_id
        errors=validate(normalize(spec))
        if errors: raise ValueError('; '.join(errors))
        root=jobs_dir/job_id
        try: root.mkdir()
        except FileExistsError: continue
        break
    else: raise ValueError('No available local job ID')
    destinations={(host,str(remote_path(remote_root)/job_id))}
    for node in bindings['nodes'].values():
        node_root=remote_path(node['work_dir'])/job_id
        node['package']=str(node_root/'common/skill-snapshot')
        destinations.add((node['host'],str(node_root)))
    plan(spec,root)
    inputs=root/'common/inputs';inputs.mkdir()
    (inputs/'bindings.json').write_text(json.dumps(bindings,indent=2),encoding='utf-8')
    files={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(root.rglob('*')) if p.is_file()}
    (root/'common/bundle-manifest.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
    archive=jobs_dir/(job_id+'.tar.gz')
    with tarfile.open(archive,'w:gz') as tar:
        for p in sorted(root.iterdir()): tar.add(p,arcname=p.name)
    return root,archive,sorted(destinations)


def upload(host, destination, archive):
    remote_path(destination)
    ssh(host,['mkdir','-p',str(PurePosixPath(destination).parent)])
    # Exclusive directory creation: never merge into an existing task.
    ssh(host,['mkdir',destination])
    target=destination+'/bundle.tar.gz'
    subprocess.run(['scp',str(archive),host+':'+shlex.quote(target)],check=True)
    expected=hashlib.sha256(archive.read_bytes()).hexdigest()
    if ssh(host,['sha256sum',target]).split()[0]!=expected: raise ValueError('Upload digest mismatch')
    ssh(host,['tar','-xzf',target,'-C',destination])
    verify="import hashlib,json,pathlib,sys; r=pathlib.Path(sys.argv[1]); m=json.loads((r/'common/bundle-manifest.json').read_text()); assert all(hashlib.sha256((r/k).read_bytes()).hexdigest()==v for k,v in m.items()), 'Bundle file digest mismatch'"
    ssh(host,['python3','-c',verify,destination])
    ssh(host,['rm','--',target])


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=['prepare','submit','status'])
    ap.add_argument('--host',required=True);ap.add_argument('--remote-root',required=True)
    ap.add_argument('--job-spec',type=Path);ap.add_argument('--bindings',type=Path)
    ap.add_argument('--date');ap.add_argument('--local-jobs-dir',type=Path,default=Path('D:/autobenchmark-local/jobs'))
    a=ap.parse_args();remote_path(a.remote_root)
    if a.action!='prepare':
        print(ssh(a.host,['python3',a.remote_root+'/common/skill-snapshot/scripts/submission.py',a.action,'--run-dir',a.remote_root]));return
    if not all([a.job_spec,a.bindings,a.date]): ap.error('prepare requires job-spec, bindings and date')
    root,archive,destinations=build(a.job_spec,a.bindings,a.local_jobs_dir,a.date,a.host,a.remote_root)
    for host,destination in destinations: upload(host,destination,archive)
    run=str(remote_path(a.remote_root)/root.name)
    print(json.dumps({'job_id':root.name,'run_dir':run,'local_dir':str(root)}),flush=True)
    print(ssh(a.host,['python3',run+'/common/skill-snapshot/scripts/preflight.py','--run-dir',run,'--bindings',run+'/common/inputs/bindings.json']))

if __name__=='__main__': main()
