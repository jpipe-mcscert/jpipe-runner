import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestCircularDependencyE2E(unittest.TestCase):
    """
    End-to-end tests for circular_dependency pipeline.
    """

    def setUp(self):
        self.test_dir = Path(__file__).parent / "resources" / "circular_dependency"
        self.justification_file = self.test_dir / "circular.json"
        self.python_file = self.test_dir / "circular.py"
        self.justification_name = "circular"

        self.validators = [
            "ExecutionOrder",
        ]

        self.assertTrue(self.justification_file.exists(), f"Justification file not found: {self.justification_file}")
        self.assertTrue(self.python_file.exists(), f"Python file not found: {self.python_file}")

    def _run_jpipe_runner(self, additional_args=None, expected_exit_code=1):
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

    def test_circular_dependency_normal_execution(self):
        """Test execution with circular dependency, should always fail."""
        result = self._run_jpipe_runner()
        self.assertTrue(result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_circular_dependency_dry_run(self):
        """Test dry run mode, should also fail due to circular dependency."""
        result = self._run_jpipe_runner(additional_args=["--dry-run"])
        self.assertTrue(result.stderr)
        self.assertEqual(result.returncode, 1)

    def test_circular_dependency_with_diagram_export(self):
        """Test diagram export functionality with circular dependency."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir)
            result = self._run_jpipe_runner(
                additional_args=[
                    "--output-path", str(output_path),
                    "--format", "svg"
                ]
            )
            output_path = output_path / self.justification_name
            expected_file = output_path.with_suffix(".svg")
            self.assertFalse(expected_file.exists(), f"Diagram file should not be generated: {expected_file}")
            self.assertTrue(result.stderr)
            self.assertEqual(result.returncode, 1)

    def test_circular_dependency_invalid_justification_fails(self):
        """
        Test that invalid justification files are properly rejected.
        """
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

    def test_circular_dependency_missing_library_fails(self):
        """
        Test that missing library files cause appropriate failure.
        """
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

    def test_circular_dependency_validation_fail(self):
        """
        Test that the circular dependency justification fails validation.
        """
        result = self._run_jpipe_runner()

        # Should not contain any validation errors
        for validator in self.validators:
            self.assertIn(validator.lower(), result.stderr.lower(),
                             f"Validation error found for {validator}")
        self.assertEqual(result.returncode, 1)

if __name__ == '__main__':
    unittest.main()
