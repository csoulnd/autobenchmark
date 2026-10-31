import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'skills/ascend-llm-deploy-eval/scripts'))
import plan_run as planner
ROOT=planner.PACKAGE

class PlanTests(unittest.TestCase):
    def setUp(self): self.spec=planner.load_json(ROOT/'examples/job_spec.single-case.json')
    def test_defaults_and_explicit_request_count(self):
        self.spec.pop('execution')
        normalized=planner.normalize(self.spec)
        self.assertEqual(planner.validate(normalized),[])
        self.assertEqual(normalized['execution']['max_retries'],3)
        self.assertEqual(normalized['execution']['smoke'],'default')
        self.assertEqual(normalized['benchmark']['case']['formal_requests'],64)
    def test_reject_conflicts(self):
        mutations=[lambda s:s['deployment']['parameters']['instances'][1].update(port=9000),
            lambda s:s['benchmark']['case'].update(id='../bad'),lambda s:s['target'].update(container='other'),
            lambda s:s['execution'].update(max_retries=4),lambda s:s['benchmark']['case'].update(formal_requests=1),
            lambda s:s['deployment'].update(recipe='../../elsewhere'),lambda s:s.update(unresolved=['missing input'])]
        for mutate in mutations:
            s=copy.deepcopy(self.spec); mutate(s)
            self.assertTrue(planner.validate(s))
    def test_idempotent_and_conflicting_plan(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            planner.plan(self.spec,root); before=(root/'plan.json').read_bytes()
            planner.plan(self.spec,root); self.assertEqual(before,(root/'plan.json').read_bytes())
            self.spec['benchmark']['case']['formal_requests']=65
            with self.assertRaises(ValueError): planner.plan(self.spec,root)
            self.assertEqual(before,(root/'plan.json').read_bytes())
    def test_recipe_not_bound_to_image_model_or_workdir(self):
        self.spec['target'].update(image='candidate:test',work_dir='/work/'+self.spec['job_id'])
        self.spec['model']['path']='/models/alternate'
        self.spec['container']['mounts']=[{'source':p,'target':p,'read_only':False} for p in ['/work','/models']]
        self.assertEqual(planner.validate(self.spec),[])
        with tempfile.TemporaryDirectory() as d:
            planner.recipe(self.spec).render(self.spec,Path(d))
            text=(Path(d)/'run_p.sh').read_text()
            self.assertIn('/models/alternate',text)
            self.assertNotIn('/home/d00937186',text)
            self.assertNotIn('DeepSeek-V4-Flash-0731',text)
    def test_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.json'; p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):planner.load_json(p)
