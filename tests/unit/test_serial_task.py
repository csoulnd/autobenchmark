"""Task orchestration tests: real plans/bindings/state, mocked external services."""
import copy
import io
from contextlib import redirect_stdout
from contextlib import nullcontext
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'skills/ascend-llm-deploy-eval/scripts'))
import plan_run
import task_preflight as preflight
import task_runtime as task
import stage_runtime as runtime


def fixture():
    dep={'id':'a','image':'test-image','model':{'id':'model','served_name':'test','max_model_len':4096},
         'npu_ids':[0],'container':{'shm_size':'1g','privileged':False},'ports':{'api':1,'rpc':2},
         'commands':[{'name':'model','argv':['server','--model','{{model.path}}','--port','{{ports.api}}'],
                      'env':{'NIC':'{{network.interface}}','IP':'{{network.ip}}'}}],
         'prefill_dp':1,'service':{'health_urls':['http://127.0.0.1:{{ports.api}}/health'],
           'endpoint':'http://127.0.0.1:{{ports.api}}','reset_ports':['{{ports.api}}'],'prefill_port':'{{ports.api}}'}}
    second=copy.deepcopy(dep); second['id']='b'; second['commands'][0]['argv']+=['--other-mode']
    return {'schema_version':'3.0','job_id':'20261101-101','state':'ready','target':{'host':'test.invalid'},
       'deployments':[dep,second], 'cases':[{'id':name,'deployment_id':dep_id,'input_tokens':32,'output_tokens':8,
       'concurrency':concurrency,'prefix_ratio':0.5} for name,dep_id,concurrency in [('c1','a',1),('c2','a',2),('c3','b',1)]],
       'unresolved':[]}


class SerialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name); self.root=self.base/'task'
        self.model=self.base/'weights with spaces'; self.model.mkdir()
        self.spec=fixture()
        plan_run.plan(self.spec,self.root)
        self.bindings=self.base/'bindings.json'
        runtime.save(self.bindings,{'model_paths':{'model':str(self.model)},'network_interface':'verified-nic'})

    def preflight(self):
        with patch.object(preflight,'discover_network',return_value={'interface':'verified-nic','ip':'10.2.3.4'}), \
             patch.object(preflight,'command',return_value=json.dumps([{'Id':'sha256:test'}])), \
             patch.object(preflight,'inspect_image_tools',return_value={'aisbench_work_path':'/discovered/benchmark','version':'test'}), \
             patch('preflight.check',return_value={'status':'PASSED'}):
            return preflight.prepare_task(self.root,self.bindings)

    def run_loop(self, failed_case=None, unsafe=False, fail_release=False):
        self.preflight(); calls=[]
        def deploy(root):
            action='reuse' if runtime.state(root)['service']=='READY' else 'start'
            calls.append((action,root.name))
            runtime.update(root,service='READY')
            return {'status':'PASSED','message':action,'artifacts':[]}
        def evaluate(root,case):
            calls.append(('test',case['id']))
            failed=case['id']==failed_case
            runtime.update_case(root,case['id'],status='FAILED' if failed else 'PASSED',
                attempts=[{'attempt':1,'folder':'test','status':'FAILED' if failed else 'PASSED',
                           'cleanup':{'released':not (failed and unsafe)}}],safe_to_continue=not unsafe)
            return {'status':'FAILED' if failed else 'PASSED','message':'test result','artifacts':[]}
        def release(root,policy,scope):
            calls.append(('release',root.name,policy,scope))
            if fail_release and root.name=='a' and scope=='job':raise RuntimeError('release failure')
            if policy!='keep_service':runtime.update(root,service='RELEASED')
            return {'status':'released' if policy!='keep_service' else 'kept'}
        with patch.object(task,'locked',side_effect=lambda s:nullcontext()), \
             patch('deploy.deploy',side_effect=deploy),patch('evaluate.evaluate',side_effect=evaluate), \
             patch('finalize.release',side_effect=release):
            with redirect_stdout(io.StringIO()):
                result=task.run_task(self.root)
        return result,calls,json.loads((self.root/'summary.json').read_text())

    def test_plan_default_counts_and_explicit_order(self):
        plan=json.loads((self.root/'plan.json').read_text())
        self.assertEqual([c['formal_requests'] for c in plan['job_spec']['cases']],[4,8,4])
        self.assertEqual([c['case_id'] for c in plan['sequence']],['c1','c2','c3'])
        self.assertTrue((self.root/'run.sh').exists())
        self.assertNotIn(b'\r', (self.root/'run.sh').read_bytes())
        self.assertNotIn('model_paths',json.dumps(plan['job_spec']))
        event=json.loads((self.root/'logs/config-storage-events.jsonl').read_text().splitlines()[0])
        self.assertEqual(event['storage'],'not_implemented')

    def test_preflight_resolves_ports_and_machine_values(self):
        self.preflight(); _,resolved=task.resolved_task(self.root)
        execution=json.loads((self.root/'services/a/resolved.json').read_text())
        script=(self.root/'services/a/scripts/start-model.sh').read_text()
        self.assertIn('verified-nic',script); self.assertIn('10.2.3.4',script)
        self.assertIn(str(self.model.resolve()),script); self.assertNotIn('{{',script)
        ports=[]
        for dep in resolved['deployments'].values():
            ports+=json.loads((Path(dep['run_dir'])/'resolved.json').read_text())['deployment']['service']['ports']
        self.assertEqual(len(ports),len(set(ports)))
        self.assertEqual(execution['benchmark']['aisbench_work_path'],'/discovered/benchmark')
        self.assertEqual(self.preflight()['status'],'PASSED')

    def test_loop_reuses_service_then_switches_and_finalizes(self):
        result,calls,summary=self.run_loop()
        self.assertEqual(result['status'],'PASSED')
        self.assertEqual([c for c in calls if c[0] in ['start','reuse','test']],
            [('start','a'),('test','c1'),('reuse','a'),('test','c2'),('start','b'),('test','c3')])
        self.assertIn(('release','a','stop_container','case:c2'),calls)
        self.assertEqual([c[1] for c in calls if c[0]=='release' and c[-1]=='job'],['a','b'])
        self.assertEqual(summary['evaluation_status'],'PASSED')

    def test_failed_case_does_not_hide_failure_and_next_case_runs(self):
        result,calls,summary=self.run_loop(failed_case='c1')
        self.assertEqual(result['status'],'FAILED')
        self.assertIn(('test','c2'),calls); self.assertIn(('test','c3'),calls)
        self.assertEqual(summary['cases']['c1']['status'],'FAILED')
        self.assertEqual(summary['cases']['c2']['status'],'PASSED')

    def test_unsafe_client_stops_loop_but_task_cleanup_runs(self):
        result,calls,summary=self.run_loop(failed_case='c1',unsafe=True)
        self.assertEqual(result['status'],'FAILED')
        self.assertNotIn(('test','c2'),calls)
        self.assertEqual([c[1] for c in calls if c[0]=='release' and c[-1]=='job'],['a','b'])

    def test_release_failure_does_not_skip_other_deployments(self):
        result,calls,summary=self.run_loop(fail_release=True)
        self.assertEqual(result['status'],'FAILED')
        self.assertIn(('release','b','stop_container','job'),calls)
        self.assertEqual(summary['release_status'],'FAILED')

    def test_preflight_gate_and_tamper_detection(self):
        with self.assertRaises(ValueError):task.run_task(self.root)
        self.preflight()
        (self.root/'services/a/scripts/start-model.sh').write_text('changed')
        with self.assertRaises(ValueError):task.resolved_task(self.root)

    def test_case_change_does_not_change_container_identity(self):
        self.preflight()
        execution=json.loads((self.root/'services/a/resolved.json').read_text())
        changed=copy.deepcopy(execution); changed['benchmark']['case']={'concurrency':128}
        self.assertEqual(runtime.ownership_digest(execution),runtime.ownership_digest(changed))

    def test_multiple_networks_require_a_specific_choice(self):
        interfaces=[{'ifname':n,'operstate':'UP','addr_info':[{'family':'inet','scope':'global','local':ip}]} for n,ip in [('a','10.1.0.1'),('b','10.2.0.1')]]
        with patch.object(preflight,'command',return_value=json.dumps(interfaces)):
            with self.assertRaises(ValueError):preflight.discover_network()
            self.assertEqual(preflight.discover_network('b')['ip'],'10.2.0.1')

    def test_shell_bindings_are_quoted_and_unknown_values_rejected(self):
        result=preflight.expand('source {{paths.env}}',{'paths':{'env':'/path with spaces/$(bad)'}},shell=True)
        self.assertEqual(result,"source '/path with spaces/$(bad)'")
        with self.assertRaises(ValueError):preflight.expand('{{ports.missing}}',{'ports':{}})

    def test_duplicate_or_missing_case_association_rejected(self):
        s=plan_run.normalize(fixture()); s['cases'][0]['deployment_id']='missing'
        self.assertTrue(plan_run.validate(s))
        s=plan_run.normalize(fixture()); s['cases'][1]['id']=s['cases'][0]['id']
        self.assertTrue(plan_run.validate(s))

class CaseIsolationTests(unittest.TestCase):
    def test_exhausted_case_does_not_consume_next_case_budget(self):
        import evaluate
        from types import SimpleNamespace
        task_spec=plan_run.normalize(fixture())
        spec={'execution':task_spec['execution'],'benchmark':{'tool_dir':'unused'}}
        first=copy.deepcopy(task_spec['cases'][0]); first['id']='first'
        second=copy.deepcopy(first); second['id']='second'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ['scripts','logs','results']:(root/name).mkdir()
            runtime.update(root,service='READY',container_id='test')
            calls=[]
            def attempt(argv,**kwargs):
                folder=Path(argv[-1]); case_id=folder.parent.name; calls.append((case_id,folder.name))
                success=case_id=='second'
                runtime.save(folder/'cleanup.json',{'released':True})
                runtime.save(folder/'summary.json',{'status':'PASSED' if success else 'FAILED','error':'test failure' if not success else None})
                return SimpleNamespace(returncode=0 if success else 2)
            with patch.object(evaluate,'read_plan',return_value=spec),patch.object(evaluate,'ready',return_value=True), \
                 patch.object(evaluate,'service_identity',return_value={'instance':1}),patch.object(evaluate,'prepare'), \
                 patch.object(evaluate.subprocess,'run',side_effect=attempt),patch.object(evaluate.time,'sleep'),redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):evaluate.evaluate(root,first)
                self.assertEqual(evaluate.evaluate(root,second)['status'],'PASSED')
            self.assertEqual(calls,[('first',f'attempt-{i:02}') for i in range(1,5)]+[('second','attempt-01')])
            self.assertEqual(runtime.case_state(root,'first')['status'],'FAILED')
            self.assertEqual(runtime.case_state(root,'second')['status'],'PASSED')

class ShellEntryTests(unittest.TestCase):
    setUp = SerialTests.setUp
    preflight = SerialTests.preflight
    @unittest.skipUnless(sys.platform=='linux','Generated Bash entry integration')
    def test_generated_shell_executes_loop_with_fake_services(self):
        import os,subprocess
        self.preflight()
        injection=self.base/'injection';injection.mkdir()
        (injection/'sitecustomize.py').write_text('''
import deploy,evaluate,finalize
from stage_runtime import update,update_case

def start(root):
 update(root,service='READY')
 return {'status':'PASSED','message':'fake service ready','artifacts':[]}
def measure(root,case):
 update_case(root,case['id'],status='PASSED',attempts=[{'attempt':1,'folder':'fake','status':'PASSED','cleanup':{'released':True}}],safe_to_continue=True)
 return {'status':'PASSED','message':'fake measured '+case['id'],'artifacts':[]}
def release(root,policy,scope):
 if policy!='keep_service':update(root,service='RELEASED')
 return {'status':'kept' if policy=='keep_service' else 'released'}
deploy.deploy=start
evaluate.evaluate=measure
finalize.release=release
''')
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(injection)+os.pathsep+str(self.root/'skill-snapshot/scripts'))
        result=subprocess.run(['bash',str(self.root/'run.sh')],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr+'\n'+result.stdout[-2000:])
        summary=json.loads((self.root/'summary.json').read_text())
        self.assertEqual(summary['evaluation_status'],'PASSED')
        self.assertEqual(set(summary['cases']),{'c1','c2','c3'})
        # Restarting the generated entry reuses terminal case results and only repeats cleanup.
        result=subprocess.run(['bash',str(self.root/'run.sh')],env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
