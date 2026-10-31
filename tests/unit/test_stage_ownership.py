import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'skills/ascend-llm-deploy-eval/scripts'))
from stage_runtime import digest,inspect_owned

class OwnershipTests(unittest.TestCase):
    def test_identity_and_spec_label_required(self):
        s={'job_id':'20261031-002','target':{'container':'20261031-002'}}
        good={'Id':'actual-id','Config':{'Labels':{'benchmark.job_id':s['job_id'],'benchmark.spec_sha256':digest(s)}}}
        with patch('stage_runtime.command',return_value=json.dumps([good])):
            self.assertEqual(inspect_owned(s,'actual-id')['Id'],'actual-id')
            with self.assertRaises(ValueError):inspect_owned(s,'old-id')
        for label in ['benchmark.job_id','benchmark.spec_sha256']:
            bad=json.loads(json.dumps(good)); bad['Config']['Labels'][label]='other'
            with patch('stage_runtime.command',return_value=json.dumps([bad])):
                with self.assertRaises(ValueError):inspect_owned(s,'actual-id')
