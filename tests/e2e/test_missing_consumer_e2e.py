import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestMissingConsumerE2E(unittest.TestCase):
    """
    End-to-end tests for missing_consumer file validation pipeline.
    """

    def setUp(self):
        self.test_dir = Path(__file__).parent / "resources" / "missing_consumer"
        self.justification_file = self.test_dir / "math_operation.json"
        self.python_file = self.test_dir / "math_operation.py"
        self.justification_name = "string_operations"

        self.assertTrue(self.justification_file.exists(), f"Justification file not found: {self.justification_file}")
        self.assertTrue(self.python_file.exists(), f"Python file not found: {self.python_file}")

    def _run_jpipe_runner(self, additional_args=None, expected_exit_code=0):
        cmd = [
            sys.executable, "-m", "jpipe_runner.runner",
            "--library", str(self.python_file),
            str(self.justification_file)
        ]

        if additional_args:
            cmd.extend(additional_args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.test_dir.parent.parent.parent
        )

        if result.returncode != expected_exit_code:
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            print(f"Expected exit code {expected_exit_code}, got {result.returncode}")

        self.assertEqual(result.returncode, expected_exit_code)
        return result

    def test_missing_consumer_normal_execution(self):
        """
        Test pipeline with a file that exists.
        """
        result = self._run_jpipe_runner(
            expected_exit_code=1
        )
        self.assertTrue(result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_missing_consumer_dry_run(self):
        """
        Test dry run mode to ensure no actual execution occurs.
        """
        result = self._run_jpipe_runner(additional_args=[
            "--dry-run"
        ],
            expected_exit_code=1
        )

        self.assertTrue(result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_missing_consumer_with_diagram_export(self):
        """
        Test diagram export functionality with missing_consumer failed pipeline.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir)

            result = self._run_jpipe_runner(
                additional_args=[
                    "--output-path", str(output_path),
                    "--format", "svg"
                ],
                expected_exit_code=1
            )

            output_path = output_path / self.justification_name  # output svg same name as justification name

            # Check that diagram was generated
            expected_file = output_path.with_suffix(".svg")
            self.assertTrue(not expected_file.exists(), f"Expected diagram file not found: {expected_file}")
            self.assertTrue(result.stderr)
            self.assertEqual(result.returncode, 1)

    def test_missing_consumer_invalid_justification_fails(self):
        """
        Test that invalid justification files are properly rejected.
        """
        # Create a temporary invalid justification file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"invalid": "structure"}, f)
            invalid_file = f.name

        try:
            cmd = [
                sys.executable, "-m", "jpipe_runner.runner",
                "--library", str(self.python_file),
                invalid_file
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.test_dir.parent.parent.parent
            )

            # Should fail with validation error
            self.assertTrue(result.stderr)
            self.assertTrue(result.stderr, "Expected validation error not found in stderr")
            self.assertEqual(result.returncode, 1)

        finally:
            os.unlink(invalid_file)

    def test_missing_consumer_missing_library_fails(self):
        """Test that missing library files cause appropriate failure."""
        cmd = [
            sys.executable, "-m", "jpipe_runner.runner",
            "--library", "nonexistent_file.py",
            str(self.justification_file)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.test_dir.parent.parent.parent
        )

        self.assertTrue(result.stderr)
        self.assertEqual(result.returncode, 1)


if __name__ == '__main__':
    unittest.main()
