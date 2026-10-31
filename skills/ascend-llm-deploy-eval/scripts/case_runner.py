"""One AISBench attempt inside the owned container; always release its client/links."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
from service_process import members,ticks
from validate_case import validate


def run(root,folder):
    spec=json.loads((root/'job_spec.json').read_text())
    case=spec['benchmark']['case']; service=json.loads((root/'scripts/service.json').read_text())
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def http(port,path,method='GET'):
        with opener.open(urllib.request.Request(f'http://127.0.0.1:{port}{path}',method=method),timeout=30) as r:
            return r.read().decode()
    case=dict(case,prefill_dp=spec['benchmark']['prefill_dp'],reset_ports=service['reset_ports'])
    (folder/'case.json').write_text(json.dumps(case,indent=2))
    work=Path(spec['benchmark']['aisbench_work_path'])
    links=[work/'ais_bench/datasets/gsm8k/test.jsonl',work/'ais_bench/benchmark/configs/models/vllm_api/vllm_api_chat_temp.py']
    # Existing files are never ours to remove. Stop without retry if ownership unclear.
    for link in links:
        if link.exists() or link.is_symlink():
            (folder/'cleanup.json').write_text(json.dumps({'released':False,'error':'Existing link/file: '+str(link)}))
            raise ValueError('Existing tool link/file; reconcile before running')
    tool=folder/'tool'; datasets=folder/'datasets'; datasets.mkdir()
    from urllib.parse import urlsplit
    endpoint=urlsplit(service['endpoint'])
    config={'DATASET_PATH':str(datasets),'WORK_PATH':str(work),'MODEL_NAME':spec['model']['served_name'],
        'MODEL_PATH':spec['model']['path'],'HOST_IP':endpoint.hostname,'HOST_PORT':str(endpoint.port),
        'URL':'','API_KEY':'','DEFAULT_PERFORMANCE_TEST':'default_perf','OUTPUT_DIR':'./outputs',
        'POD_INFO':[f"127.0.0.1:{service['prefill_port']}"]}
    (tool/'config.py').write_text(''.join(f'{k} = {v!r}\n' for k,v in config.items()))
    process=None; errors=[]; result=None; failure=None; started=time.monotonic()
    try:
        if case['reset_cache']:
            for port in service['reset_ports']:
                response=http(port,'/reset_prefix_cache','POST')
                (folder/f'reset-{port}-0.json').write_text(response)
                if json.loads(response).get('success') is not True: raise RuntimeError('Cache reset busy or failed')
        for port in service['reset_ports']:
            (folder/f'metrics-{port}-before.txt').write_text(http(port,'/metrics'))
        argv=['python3','aisbench_test.py','--input_len',str(case['input_tokens']),'--output_len',str(case['output_tokens']),
            '--data_num',str(case['formal_requests']),'--concurrency',str(case['concurrency']),
            '--request_rate',str(case['request_rate']),'--test_type','stream','--dataset_type','prefix_cache',
            '--prefix_num',str(case['prefix_num']),'--repeat_rate',str(case['prefix_ratio']),'--prefix_test',
            '--seed',str(case['seed']),'--dp',str(spec['benchmark']['prefill_dp']),'--npu_num',str(len(service['npu_ids']))]
        (folder/'command.json').write_text(json.dumps(argv))
        with (folder/'console.log').open('w') as log:
            process=subprocess.Popen(argv,cwd=tool,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            identity={'pid':process.pid,'start_ticks':ticks(process.pid)}
            (folder/'client.json').write_text(json.dumps(identity))
            code=process.wait(timeout=case['timeout_seconds'])
        if code: raise RuntimeError(f'Benchmark exited {code}; see console.log')
        for port in service['reset_ports']:
            (folder/f'metrics-{port}-after.txt').write_text(http(port,'/metrics'))
        result=validate(folder,case)
    except Exception as exc:
        failure=repr(exc)
    finally:
        if process is not None and members(process.pid):
            # This group was created by this invocation and cannot be confused with another client.
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL); process.wait(timeout=10)
            deadline=time.monotonic()+10
            while members(process.pid) and time.monotonic()<deadline: time.sleep(.2)
            if members(process.pid):
                os.killpg(process.pid,signal.SIGKILL); time.sleep(1)
                if members(process.pid): errors.append('Client process group remains')
        for link in links:
            try:
                if link.is_symlink() and link.resolve().is_relative_to(folder.resolve()): link.unlink()
                elif link.exists() or link.is_symlink(): raise ValueError('Tool link ownership changed: '+str(link))
            except Exception as exc: errors.append(str(exc))
        (folder/'cleanup.json').write_text(json.dumps({'released':not errors,'errors':errors,'level':'case'},indent=2))
    summary={'status':'PASSED' if result and not errors else 'FAILED','error':failure,'cleanup_errors':errors,'seconds':time.monotonic()-started}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary),flush=True)
    return 0 if summary['status']=='PASSED' else 2

if __name__=='__main__': raise SystemExit(run(Path(sys.argv[1]),Path(sys.argv[2])))
