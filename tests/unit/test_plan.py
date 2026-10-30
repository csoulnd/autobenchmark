import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2] / "skills/ascend-llm-deploy-eval"
module = importlib.util.spec_from_file_location("planner", ROOT / "scripts/plan_run.py")
planner = importlib.util.module_from_spec(module)
module.loader.exec_module(planner)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.spec = planner.load_json(ROOT / "examples/job_spec.dsv4-migration.json")

    def test_draft_structure_valid(self):
        self.assertEqual(planner.validate(self.spec), [])

    def test_reject_mutations(self):
        mutations = [
            lambda s: s.update(extra=True),
            lambda s: s["instances"][1]["device_ids"].__setitem__(0, 0),
            lambda s: s["instances"][1].update(port=9000),
            lambda s: s["instances"][0].update(tp=1),
            lambda s: s["kv_transfer"]["prefill"].update(dp=4),
            lambda s: s["benchmark"].update(prefix_caching=False),
            lambda s: s["benchmark"].update(prefill_dp=4),
            lambda s: s["benchmark"]["cases"][0].update(warmup=False),
            lambda s: s["benchmark"]["cases"][0].update(prefix_ratio=90),
            lambda s: s["benchmark"]["cases"][0].update(formal_requests=1),
            lambda s: s["benchmark"]["cases"][1].update(id="128k-50"),
            lambda s: s["model"].update(max_model_len=131072),
            lambda s: s.update(state="ready"),
            lambda s: s["policies"].update(cleanup_owned_only=False),
        ]
        for mutate in mutations:
            candidate = copy.deepcopy(self.spec)
            mutate(candidate)
            with self.subTest(candidate=candidate):
                self.assertTrue(planner.validate(candidate))

    def test_cli_draft_blocks_ready_generates_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            source, run = d / "spec.json", d / "run"
            def execute():
                source.write_text(json.dumps(self.spec), encoding="utf-8")
                return subprocess.run([sys.executable, str(ROOT / "scripts/plan_run.py"),
                                       "--job-spec", str(source), "--run-dir", str(run)],
                                      capture_output=True, text=True)
            self.assertEqual(execute().returncode, 2)
            self.assertFalse(run.exists())
            self.spec.update(state="ready", unresolved=[])
            self.spec["target"].update(host="test.invalid", container="test", work_dir="/workspace",
                                       image_id="test-fixture")
            self.spec["model"]["path"] = "/models/test"
            self.spec["benchmark"].update(tool_dir="/tools", aisbench_work_path="/benchmark")
            self.assertEqual(execute().returncode, 0)
            plan = json.loads((run / "plan.json").read_text())
            self.assertFalse(plan["runtime_verified"])
            self.assertEqual(len(plan["job_spec_sha256"]), 64)
            before = (run / "plan.json").read_bytes()
            self.assertEqual(execute().returncode, 2)
            self.assertEqual(before, (run / "plan.json").read_bytes())

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "spec.json"
            p.write_text('{"state":"draft","state":"ready"}')
            with self.assertRaises(ValueError):
                planner.load_json(p)
