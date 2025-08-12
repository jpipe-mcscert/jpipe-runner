import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from onnx.backend.test.case.node import expect


class TestExceptionHandlingE2E(unittest.TestCase):
    """
    End-to-end tests for exception_handling pipeline.
    """

    def setUp(self):
        self.test_dir = Path(__file__).parent / "resources" / "exception_handling"
        self.justification_file = self.test_dir / "error_prone.json"
        self.invalid_config_file = self.test_dir / "config_invalid_denominator.yaml"
        self.valid_config_file = self.test_dir / "config_valid_denominator.yaml"
        self.python_file = self.test_dir / "error_prone.py"
        self.justification_name = "error_prone"

        self.assertTrue(self.justification_file.exists(), f"Justification file not found: {self.justification_file}")
        self.assertTrue(self.valid_config_file.exists(), f"Config file not found: {self.valid_config_file}")
        self.assertTrue(self.invalid_config_file.exists(), f"Invalid config file not found: {self.invalid_config_file}")
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

    def test_exception_handling_valid_denominator_cmd(self):
        """Test with valid denominator via --variable."""
        result = self._run_jpipe_runner(
            additional_args=["--variable", "denominator:5"]
        )
        self.assertIn(self.justification_name, result.stdout.lower())
        self.assertEqual(result.returncode, 0)

    def test_exception_handling_valid_denominator_config(self):
        """Test with valid denominator via config file."""
        result = self._run_jpipe_runner(
            additional_args=["--config-file", str(self.valid_config_file)]
        )
        self.assertIn(self.justification_name, result.stdout.lower())
        self.assertEqual(result.returncode, 0)

    def test_exception_handling_zero_denominator(self):
        """Test with denominator=0, should raise ZeroDivisionError and fail."""
        result = self._run_jpipe_runner(
            additional_args=["--variable", "denominator:0"],
            expected_exit_code=1
        )
        self.assertIn("zero", result.stderr.lower())
        self.assertEqual(result.returncode, 1)

    def test_exception_handling_invalid_denominator_config(self):
        """Test with valid denominator via config file."""
        result = self._run_jpipe_runner(
            additional_args=["--config-file", str(self.invalid_config_file)],
            expected_exit_code=1
        )
        self.assertIn(self.justification_name, result.stdout.lower())
        self.assertEqual(result.returncode, 1)


    def test_exception_handling_missing_denominator(self):
        """Test with missing denominator, should fail validation."""
        result = self._run_jpipe_runner(
            expected_exit_code=1
        )
        self.assertTrue(result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_exception_handling_invalid_denominator_type(self):
        """Test with invalid denominator type (string), should fail."""
        result = self._run_jpipe_runner(
            additional_args=["--variable", "denominator:abc"],
            expected_exit_code=1
        )
        self.assertTrue(result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_exception_handling_dry_run(self):
        """Test dry run mode."""
        result = self._run_jpipe_runner(
            additional_args=["--variable", "denominator:10", "--dry-run"]
        )
        self.assertFalse(result.stderr)
        self.assertEqual(result.returncode, 0)

    def test_exception_handling_with_diagram_export(self):
        """Test diagram export functionality."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir)
            result = self._run_jpipe_runner(
                additional_args=[
                    "--variable", "denominator:2",
                    "--output-path", str(output_path),
                    "--format", "svg"
                ]
            )
            output_path = output_path / self.justification_name
            expected_file = output_path.with_suffix(".svg")
            self.assertTrue(expected_file.exists(), f"Expected diagram file not found: {expected_file}")
            self.assertEqual(result.returncode, 0)

    def test_exception_handling_invalid_justification_fails(self):
        """Test that invalid justification files are properly rejected."""
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
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stderr, "Expected validation error not found in stderr")
        finally:
            os.unlink(invalid_file)

    def test_exception_handling_missing_library_fails(self):
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
        self.assertNotEqual(result.returncode, 0)

if __name__ == '__main__':
    unittest.main()
