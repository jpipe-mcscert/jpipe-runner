import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestSkipScenarioE2E(unittest.TestCase):
    """End-to-end tests for skip scenario functionality."""

    def setUp(self):
        """Set up test environment with resource paths."""
        self.test_dir = Path(__file__).parent / "resources" / "skip_scenario"
        self.justification_file = self.test_dir / "conditional.json"
        self.config_file = self.test_dir / "config.yaml"
        self.python_file = self.test_dir / "conditional.py"
        self.justification_name = "conditional"

        self.validators = [
            "MissingVariableValidator",
            "SelfDependencyValidator",
            "OrderValidator",
            "ProducedButNotConsumedValidator",
            "DuplicateProducerValidator",
            "EvidenceDependencyValidator",
        ]

        self.assertTrue(self.justification_file.exists(), f"Justification file not found: {self.justification_file}")
        self.assertTrue(self.config_file.exists(), f"Config file not found: {self.config_file}")
        self.assertTrue(self.python_file.exists(), f"Python file not found: {self.python_file}")

    def _run_jpipe_runner(self, additional_args=None, expected_exit_code=0):
        """
        Helper method to run jpipe-runner with common arguments.

        :param additional_args: Additional command line arguments
        :param expected_exit_code: Expected exit code (0 for success, 1 for failure)
        :return: CompletedProcess result
        """
        cmd = [
            sys.executable, "-m", "jpipe_runner.runner",
            "--config-file", str(self.config_file),
            "--library", str(self.python_file),
            str(self.justification_file)
        ]

        if additional_args:
            cmd.extend(additional_args)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=self.test_dir.parent.parent.parent  # Run from project root
        )

        if result.returncode != expected_exit_code:
            print(f"STDOUT:\n{result.stdout}")
            print(f"STDERR:\n{result.stderr}")
            print(f"Expected exit code {expected_exit_code}, got {result.returncode}")

        self.assertEqual(result.returncode, expected_exit_code)
        return result

    def test_skip_scenario_normal_execution(self):
        """Test normal execution without skip conditions."""
        result = self._run_jpipe_runner()
        self.assertIn(self.justification_name, result.stdout.lower())
        self.assertEqual(result.returncode, 0)

    def test_skip_scenario_dry_run(self):
        """Test dry run mode to ensure no actual execution occurs."""
        result = self._run_jpipe_runner(additional_args=["--dry-run"])
        self.assertFalse(result.stderr)
        self.assertEqual(result.returncode, 0)

    def test_skip_scenario_with_diagram_export(self):
        """Test diagram export functionality with skip scenario."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir)

            result = self._run_jpipe_runner(
                additional_args=[
                    "--output-path", str(output_path),
                    "--format", "svg"
                ]
            )

            output_path = output_path / self.justification_name  # output svg same name as justification name

            # Check that diagram was generated
            expected_file = output_path.with_suffix(".svg")
            self.assertTrue(expected_file.exists(), f"Expected diagram file not found: {expected_file}")
            self.assertEqual(result.returncode, 0)

    def test_skip_scenario_validation_passes(self):
        """Test that the skip scenario justification passes validation."""
        result = self._run_jpipe_runner()

        # Should not contain any validation errors
        for validator in self.validators:
            self.assertNotIn(validator.lower(), result.stderr.lower(),
                             f"Validation error found for {validator}")
        self.assertEqual(result.returncode, 0)

    def test_skip_scenario_invalid_justification_fails(self):
        """Test that invalid justification files are properly rejected."""
        # Create a temporary invalid justification file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"invalid": "structure"}, f)
            invalid_file = f.name

        try:
            cmd = [
                sys.executable, "-m", "jpipe_runner.runner",
                "--config-file", str(self.config_file),
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

    def test_skip_scenario_missing_library_fails(self):
        """Test that missing library files cause appropriate failure."""
        cmd = [
            sys.executable, "-m", "jpipe_runner.runner",
            "--config-file", str(self.config_file),
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
