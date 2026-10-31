import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'skills/ascend-llm-deploy-eval/scripts'))
import evaluate
import stage_runtime as runtime
from plan_run import load_json

class LifecycleTests(unittest.TestCase):
    def exercise(self,success_at=None,safe=True):
        spec=load_json(runtime.PACKAGE/'examples/job_spec.single-case.json')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ['scripts','logs','results']:(root/name).mkdir()
            runtime.update(root,service='READY',container_id='test',smoke_identity={'identity':1})
            calls=[]
            def attempt(argv,**kwargs):
                folder=Path(argv[-1]); n=len(calls)+1; calls.append(n)
                passed=n==success_at
                runtime.save(folder/'cleanup.json',{'released':safe})
                runtime.save(folder/'summary.json',{'status':'PASSED' if passed else 'FAILED','error':None if passed else 'test failure'})
                return SimpleNamespace(returncode=0 if passed else 2)
            with patch.object(evaluate,'read_plan',return_value=spec),patch.object(evaluate,'ready',return_value=True),patch.object(evaluate,'service_identity',return_value={'identity':1}),patch.object(evaluate,'prepare'),patch.object(evaluate,'release'),patch.object(evaluate.subprocess,'run',side_effect=attempt),patch.object(evaluate.time,'sleep'):
                if success_at:
                    self.assertEqual(evaluate.evaluate(root)['status'],'PASSED')
                else:
                    with self.assertRaises((ValueError,RuntimeError)):evaluate.evaluate(root)
            return calls,runtime.state(root)
    def test_four_attempts_total_and_evidence_retained(self):
        calls,state=self.exercise()
        self.assertEqual(calls,[1,2,3,4]); self.assertEqual(state['case_status'],'FAILED')
        self.assertEqual(len({a['folder'] for a in state['attempts']}),4)
    def test_retry_stops_on_success(self):
        calls,state=self.exercise(success_at=2)
        self.assertEqual(calls,[1,2]); self.assertEqual(state['case_status'],'PASSED')
    def test_unsafe_cleanup_not_retried(self):
        calls,state=self.exercise(safe=False)
        self.assertEqual(calls,[1]); self.assertEqual(state['case_status'],'FAILED')
    def test_stale_smoke_invalidates_ready(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'logs').mkdir()
            runtime.update(root,service='READY',smoke_identity={'pid':1})
            with patch.object(runtime,'service_identity',return_value={'pid':2}):
                self.assertFalse(runtime.ready(root,{}))
            self.assertEqual(runtime.state(root)['service'],'UNKNOWN')

class ReleaseTests(unittest.TestCase):
    def test_stop_clears_process_registry_and_repeat_is_safe(self):
        import finalize
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'logs').mkdir()
            runtime.update(root,service='READY',container_id='cid',image_id='image')
            runtime.save(root/'service-processes.json',[{'pid':42,'start_ticks':'123'}])
            c={'Id':'cid','Image':'image','State':{'Running':False,'Pid':0}}
            with patch.object(finalize,'read_plan',return_value={}),patch.object(finalize,'inspect_owned',return_value=c),patch.object(finalize,'command',return_value='No running processes found in NPU 0'):
                finalize.release(root,'stop_container','job')
                finalize.release(root,'stop_container','job')
            self.assertEqual(json.loads((root/'service-processes.json').read_text()),[])
            self.assertEqual(runtime.state(root)['service'],'RELEASED')
            self.assertEqual(len(runtime.state(root)['releases']),2)

class DeploymentRetryTests(unittest.TestCase):
    def test_bounded_deploy_retry(self):
        import deploy
        import finalize
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); (root/'logs').mkdir(); (root/'results').mkdir()
            with patch.object(deploy,'read_plan',return_value={'execution':{'max_retries':3}}),patch.object(deploy,'ready',return_value=False),patch.object(deploy,'deploy_once',side_effect=RuntimeError('test startup failure')) as start,patch.object(finalize,'release') as release,patch.object(deploy.time,'sleep'):
                with self.assertRaises(RuntimeError):deploy.deploy(root)
                self.assertEqual(start.call_count,4); self.assertEqual(release.call_count,4)
            self.assertEqual(len(runtime.state(root)['deploy_attempts']),4)
    def test_ownership_not_retried(self):
        import deploy
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(deploy,'read_plan',return_value={'execution':{'max_retries':3}}),patch.object(deploy,'ready',return_value=False),patch.object(deploy,'deploy_once',side_effect=ValueError('ownership')) as start:
                with self.assertRaises(ValueError):deploy.deploy(root)
                self.assertEqual(start.call_count,1)

class LockTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux','Linux flock integration')
    def test_container_lock_excludes_other_process_and_releases(self):
        import os
        import subprocess
        spec={'target':{'container':'unit-lock-'+str(os.getpid())}}
        code='import json; from stage_runtime import locked\nspec=json.loads('+repr(json.dumps(spec))+')\nwith locked(spec): print("acquired")'
        with runtime.locked(spec):
            child=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
            self.assertNotEqual(child.returncode,0)
            self.assertIn('Container is locked',child.stderr)
        child=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True)
        self.assertEqual(child.returncode,0,child.stderr)
