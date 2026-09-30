import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from test_replan import checkpoint_fixture
from ontime.input import problem_to_dict


class CheckpointCLITests(unittest.TestCase):
    def test_malformed_plan_json_has_clean_input_error_exit(self):
        problem, _ = checkpoint_fixture()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'input.json').write_text(json.dumps(problem_to_dict(problem)),encoding='utf-8')
            (folder/'plan.json').write_text('[]',encoding='utf-8')
            run = subprocess.run([sys.executable,str(ROOT/'run_ontime.py'),'replan',str(folder/'input.json'),
                                  str(folder/'plan.json'),'--checkpoint-s','50','--unavailable-vehicle','U1',
                                  '--output-dir',str(folder/'out')],capture_output=True,text=True)
            self.assertEqual(run.returncode,2,run.stderr)
            self.assertNotIn('Traceback',run.stderr)
            self.assertFalse((folder/'out').exists())

    def test_cli_replan_exports_unapproved_candidate_and_rejects_active_failure(self):
        problem, baseline = checkpoint_fixture()
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder/'input.json').write_text(json.dumps(problem_to_dict(problem)),encoding='utf-8')
            (folder/'plan.json').write_text(json.dumps({'plan_input':baseline.to_dict(),
                                                       'mode':baseline.mode,'seed':baseline.seed}),encoding='utf-8')
            command=[sys.executable,str(ROOT/'run_ontime.py'),'replan',str(folder/'input.json'),
                     str(folder/'plan.json'),'--checkpoint-s','50','--seed','2026',
                     '--output-dir',str(folder/'replan'),'--unavailable-vehicle']
            success=subprocess.run([*command,'U1'],capture_output=True,text=True)
            self.assertEqual(success.returncode,0,success.stderr)
            saved=json.loads((folder/'replan/replan.json').read_text(encoding='utf-8'))
            self.assertTrue(saved['validation']['valid'])
            self.assertEqual(saved['approval_status'],'not_approved')
            self.assertFalse(saved['execution_started'])
            self.assertTrue((folder/'replan/combined/checks.csv').exists())
            rejected=subprocess.run([*command,'U2'],capture_output=True,text=True)
            self.assertEqual(rejected.returncode,2)
            self.assertIn('Active-device failure',rejected.stderr)


if __name__=='__main__':
    unittest.main()
