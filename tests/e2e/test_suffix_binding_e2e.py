import subprocess
import sys
import unittest
from pathlib import Path


class TestSuffixBindingE2E(unittest.TestCase):
    """
    End-to-end tests for @jpipe_link segment-suffix binding.

    The justification contains an evidence node whose canonical id is the
    fully-qualified "rigor:r17:e_metric". The implementing function is bound by only
    the trailing segment "e_metric" — so the pipeline runs clean only if suffix
    resolution works.
    """

    def setUp(self):
        self.test_dir = Path(__file__).parent / "resources" / "suffix_binding"
        self.justification_file = self.test_dir / "metrics.json"
        self.python_file = self.test_dir / "metrics.py"
        self.justification_name = "suffix_binding"

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

    def test_suffix_bound_pipeline_runs_and_passes(self):
        """The suffix-bound evidence node executes and the pipeline passes."""
        result = self._run_jpipe_runner()
        self.assertIn(self.justification_name, result.stdout.lower())
        # The fully-qualified node executed (PASS), proving suffix resolution worked.
        self.assertIn("rigor:r17:e_metric", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_suffix_bound_validation_is_clean(self):
        """No UnboundElementValidator error for the suffix-bound evidence node."""
        result = self._run_jpipe_runner()
        self.assertNotIn("unboundelementvalidator", result.stderr.lower())
        self.assertNotIn("unbound pipeline element", result.stderr.lower())
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
