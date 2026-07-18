import subprocess
import sys
import unittest
from pathlib import Path


class TestSimpleImportE2E(unittest.TestCase):
    """
    End-to-end tests for the "simple_import" pipeline.

    These tests validate that the jpipe runner can correctly import and execute
    a pipeline that relies on different import styles:
    - a root-level module (root_utils)
    - a nested package module (steps.step_utils)
    - Top-level imports (module load time)
    - Runtime imports (inside a function)
    """

    def setUp(self):
        self.test_dir = Path(__file__).parent / "resources" / "simple_import"
        self.justification_file = self.test_dir / "math_operation.json"
        self.python_file = self.test_dir / "steps" / "math_operation.py"
        self.justification_name = "math_operation"
        self.assertTrue(
            self.justification_file.exists(),
            f"Justification file not found: {self.justification_file}",
        )
        self.assertTrue(self.python_file.exists(), f"Python file not found: {self.python_file}")

    def _run_jpipe_runner(self, additional_args=None, expected_exit_code=0, cwd=None):
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
            cmd, capture_output=True, text=True, cwd=cwd or self.test_dir.parent.parent.parent
        )

        if result.returncode != expected_exit_code:
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            print(f"Expected exit code {expected_exit_code}, got {result.returncode}")

        self.assertEqual(result.returncode, expected_exit_code)
        return result

    def test_simple_import_normal_execution(self):
        """
        Test that the pipeline succeeds when the test directory is explicitly added to --python-path.

        This test passes "--python-path" pointing to self.test_dir, which ensures that
        you can import modules from the test directory regardless of the current working directory.
        """
        result = self._run_jpipe_runner(
            additional_args=[
                "--python-path",
                str(self.test_dir),
            ]
        )
        self.assertIn(self.justification_name, result.stdout.lower())
        self.assertEqual(result.returncode, 0)

    def test_simple_import_cwd_execution(self):
        """
        Test that the pipeline succeeds when executed with the test directory as the current working directory.

        This test does not pass any additional python paths, but instead sets the current working directory to self.test_dir.
        This verifies that the runner can resolve imports when no explicit python path is provided.
        """
        result = self._run_jpipe_runner(
            cwd=self.test_dir,
        )
        self.assertIn(self.justification_name, result.stdout.lower())
        self.assertEqual(result.returncode, 0)

    def test_simple_import_failure_no_path(self):
        """
        Test that the pipeline fails when the test directory is missing from python path and CWD isn't set.

        This verifies that executing the runner without properly configuring imports
        results in a failure during module load or execution.
        """
        result = self._run_jpipe_runner(
            expected_exit_code=1,
        )
        self.assertTrue(result.stderr)
        self.assertIn("ModuleNotFoundError", result.stderr)
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
