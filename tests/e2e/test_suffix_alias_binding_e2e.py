import subprocess
import sys
import unittest
from pathlib import Path


class TestSuffixAliasBindingE2E(unittest.TestCase):
    """
    End-to-end test for @jpipe_link suffix matching against a node *alias*.

    The evidence node's canonical id is "rigor:unified_0", which does not contain the
    suffix "e_metric" used to bind it — the suffix only appears in the alias
    "rigor:r17:e_metric". The pipeline runs clean only if suffix resolution walks the
    alias index and returns the canonical node id (combined #93 + #94 behaviour).
    """

    def setUp(self):
        self.test_dir = Path(__file__).parent / "resources" / "suffix_alias_binding"
        self.justification_file = self.test_dir / "metrics.json"
        self.python_file = self.test_dir / "metrics.py"
        self.justification_name = "suffix_alias_binding"

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

    def test_suffix_of_alias_binds_canonical_node(self):
        """A suffix of an alias binds the canonical node; the pipeline passes."""
        result = self._run_jpipe_runner()
        self.assertIn(self.justification_name, result.stdout.lower())
        # The canonical node executed (PASS), proving suffix-via-alias resolution.
        self.assertIn("rigor:unified_0", result.stdout)
        self.assertEqual(result.returncode, 0)

    def test_suffix_of_alias_validation_is_clean(self):
        """No UnboundElementValidator error for the suffix-via-alias binding."""
        result = self._run_jpipe_runner()
        self.assertNotIn("unboundelementvalidator", result.stderr.lower())
        self.assertNotIn("unbound pipeline element", result.stderr.lower())
        self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
