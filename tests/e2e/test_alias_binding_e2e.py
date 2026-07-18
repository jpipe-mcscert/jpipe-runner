import subprocess
import sys
import unittest
from pathlib import Path


class TestAliasBindingE2E(unittest.TestCase):
    """
    End-to-end tests for @jpipe_link binding on node aliases.

    The justification contains a unified evidence node whose canonical id is
    "rigor:unified_0" and which carries two aliases. The implementing function is
    bound by *both* aliases (stacked @jpipe_link decorators), neither of which is
    the canonical id — so the pipeline only runs clean if alias resolution and
    multiple annotations per function both work.
    """

    def setUp(self):
        self.test_dir = Path(__file__).parent / "resources" / "alias_binding"
        self.justification_file = self.test_dir / "metrics.json"
        self.python_file = self.test_dir / "metrics.py"
        self.justification_name = "alias_binding"

        self.assertTrue(
            self.justification_file.exists(),
            f"Justification file not found: {self.justification_file}",
        )
        self.assertTrue(
            self.python_file.exists(), f"Python file not found: {self.python_file}"
        )

    def _run_jpipe_runner(self, additional_args=None, expected_exit_code=0):
        cmd = [
            sys.executable,
            "-m",
            "jpipe_runner.runner",
            "--library",
            str(self.python_file),
            str(self.justification_file),
        ]
        if additional_args:
            cmd.extend(additional_args)

        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=self.test_dir.parent.parent.parent
        )

        if result.returncode != expected_exit_code:
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            print(f"Expected exit code {expected_exit_code}, got {result.returncode}")

        self.assertEqual(result.returncode, expected_exit_code)
        return result

    def test_alias_bound_pipeline_runs_and_passes(self):
        """The alias-bound evidence node executes and the pipeline passes."""
        result = self._run_jpipe_runner()
        self.assertIn(self.justification_name, result.stdout.lower())
        # The unified evidence node executed (PASS), proving alias resolution worked.
        self.assertIn("rigor:unified_0", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_alias_bound_validation_is_clean(self):
        """No UnboundElementValidator error for the alias-bound evidence node."""
        result = self._run_jpipe_runner()
        self.assertNotIn("unboundelementvalidator", result.stderr.lower())
        self.assertNotIn("unbound pipeline element", result.stderr.lower())
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
