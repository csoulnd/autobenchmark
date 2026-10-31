"""DSV4 P/D candidate recipe. Model/image compatibility is checked during intake.

The two shell assets preserve tested tuning; render replaces task-specific values
as argument arrays, never by interpolating user strings into shell commands.
"""
import ipaddress
import json
from pathlib import Path
import re
import shlex
import shutil


def validate(spec):
    p = spec['deployment']['parameters']
    ipaddress.ip_address(p['network']['ip'])
    if not re.fullmatch(r'[a-zA-Z0-9_.:-]+', p['network']['interface']):
        raise ValueError('Invalid network interface')
    instances = p['instances']
    if len(instances) != 2 or {i['role'] for i in instances} != {'prefill', 'decode'}:
        raise ValueError('DSV4 PD recipe requires one prefill and one decode')
    devices, ports = set(), {p['proxy_port']}
    for i in instances:
        if len(i['device_ids']) != i['dp']*i['tp'] or devices.intersection(i['device_ids']):
            raise ValueError('Invalid DP/TP device allocation')
        devices.update(i['device_ids'])
        for k in ['port','kv_port','dp_rpc_port']:
            if not isinstance(i[k],int) or not 0 < i[k] < 65536 or i[k] in ports:
                raise ValueError('Invalid or conflicting port')
            ports.add(i[k])
    if spec['benchmark']['prefill_dp'] != next(i['dp'] for i in instances if i['role']=='prefill'):
        raise ValueError('Warmup DP differs from prefill DP')
    if not p['prefix_caching']:
        raise ValueError('Selected prefix benchmark needs prefix caching')
    if not Path(p['comm_path']).is_absolute():
        # PurePosixPath is used by plan_run on Windows; string check here.
        if not p['comm_path'].startswith('/'):
            raise ValueError('Communication configuration must be absolute')
    return sorted(devices), sorted(ports)


def render(spec, output):
    devices, ports = validate(spec)
    p=spec['deployment']['parameters']; root=spec['target']['work_dir']
    source=Path(__file__).parent
    output.mkdir(parents=True,exist_ok=True)
    commands=[]
    for i in p['instances']:
        name='run_p.sh' if i['role']=='prefill' else 'run_d.sh'
        text=(source/name).read_text()
        header, body=text.split('vllm serve ',1)
        header=re.sub(r'^nic_name=.*$', 'nic_name='+shlex.quote(p['network']['interface']),header,flags=re.M)
        header=re.sub(r'^local_ip=.*$', 'local_ip='+shlex.quote(p['network']['ip']),header,flags=re.M)
        header=re.sub(r'^export ASCEND_LOCAL_COMM_RES_PATH=.*$', 'export ASCEND_LOCAL_COMM_RES_PATH='+shlex.quote(p['comm_path']+'/'),header,flags=re.M)
        argv=shlex.split('vllm serve '+body.split('2>&1 | tee',1)[0].replace('\\\n',' '))
        argv[2]=spec['model']['path']
        def arg(flag,value):
            argv[argv.index(flag)+1]=str(value)
        for flag,value in {'--device-ids':','.join(map(str,i['device_ids'])), '--port':i['port'],
            '--data-parallel-size':i['dp'],'--tensor-parallel-size':i['tp'],
            '--data-parallel-address':p['network']['ip'],'--data-parallel-rpc-port':i['dp_rpc_port'],
            '--max_model_len':spec['model']['max_model_len'],'--served-model-name':spec['model']['served_name']}.items():
            arg(flag,value)
        if not i['ep']:
            argv.remove('--enable-expert-parallel')
        profiler=json.loads(argv[argv.index('--profiler-config')+1]); profiler['torch_profiler_dir']=root+'/logs/profiler'
        arg('--profiler-config',json.dumps(profiler))
        kv=json.loads(argv[argv.index('--kv-transfer-config')+1])
        kv.update(kv_connector=p['connector'],kv_port=str(i['kv_port']),engine_id=i['engine_id'])
        kv['kv_connector_extra_config']={'ascend_local_comm_res_path':p['comm_path'],
            **{j['role']:{'dp_size':j['dp'],'tp_size':j['tp']} for j in p['instances']}}
        arg('--kv-transfer-config',json.dumps(kv))
        (output/name).write_text(header+'\nexec '+shlex.join(argv)+'\n')
        commands.append({'name':i['role'],'argv':['bash',root+'/scripts/'+name]})
    shutil.copy2(source/'load_balance_proxy_server_example.py',output)
    byrole={i['role']:i for i in p['instances']}
    commands.append({'name':'proxy','argv':['python3',root+'/scripts/load_balance_proxy_server_example.py',
        '--host','127.0.0.1','--port',str(p['proxy_port']),
        '--prefiller-hosts','127.0.0.1','--prefiller-ports',str(byrole['prefill']['port']),
        '--decoder-hosts','127.0.0.1','--decoder-ports',str(byrole['decode']['port'])]})
    result={'commands':commands,'npu_ids':devices,'ports':ports,
      'health_urls':[f"http://127.0.0.1:{i['port']}/health" for i in p['instances']],
      'endpoint':f"http://127.0.0.1:{p['proxy_port']}",
      'reset_ports':[i['port'] for i in p['instances']],
      'prefill_port':byrole['prefill']['port'],'network':p['network']}
    (output/'service.json').write_text(json.dumps(result,indent=2))
    return result
