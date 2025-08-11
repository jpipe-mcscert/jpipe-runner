import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestComplexSuccessE2E(unittest.TestCase):
    """End-to-end tests for complex success data pipeline functionality."""

    def setUp(self):
        """Set up test environment with resource paths."""
        self.test_dir = Path(__file__).parent / "resources" / "complex_success"
        self.justification_file = self.test_dir / "data_pipeline.json"
        self.config_file = self.test_dir / "config.yaml"
        self.python_file = self.test_dir / "data_pipeline.py"
        self.justification_name = "vaccination_campaign"

        self.validators = [
            "MissingVariableValidator",
            "SelfDependencyValidator",
            "OrderValidator",
            "ProducedButNotConsumedValidator",
            "DuplicateProducerValidator",
            "EvidenceDependencyValidator",
        ]

        # Ensure all required files exist
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

    def test_complex_success_normal_execution(self):
        """Test normal execution of complex data pipeline."""
        result = self._run_jpipe_runner(
            additional_args=["--config-file", str(self.config_file)]
        )
        # Check that execution completed successfully
        self.assertIn(self.justification_name, result.stdout.lower())
        self.assertEqual(result.returncode, 0)

    def test_complex_success_with_valid_data(self):
        """Test execution with valid input data that should pass all stages."""
        result = self._run_jpipe_runner(
            additional_args=[
                "--variable", "press_release_path:e2e/resources/complex_success/data/press_release.txt",
                "--variable", "social_posts_path:e2e/resources/complex_success/data/social_posts.json",
                "--variable", "event_calendar_path:e2e/resources/complex_success/data/event_calendar.csv",
                "--variable", "speakers_list_path:e2e/resources/complex_success/data/speakers_list.csv",
                "--variable", "fleet_info_path:e2e/resources/complex_success/data/fleet_info.json",
                "--variable", "staff_roster_path:e2e/resources/complex_success/data/staff_roster.csv",
                "--variable", "schedule_plan_path:e2e/resources/complex_success/data/schedule_plan.txt",
                "--variable", "leader_commitments_path:e2e/resources/complex_success/data/leader_commitments.txt",
                "--variable", "testimonial_videos_path:e2e/resources/complex_success/data/testimonial_videos_list.txt",
                "--variable", "safety_report_path:e2e/resources/complex_success/data/safety_report.pdf",
                "--variable", "faq_document_path:e2e/resources/complex_success/data/faq_document.txt",
                "--variable",
                'settings: {"retries": 3, "enable_logging": true, "thresholds": {"pass_size": 50, "min_lines": 3}, "options": {"verbose": "True", "debug_mode": false}}',
                '--variable',
                'metadata: {"version": "1.0", "authors": [{"name": "Jane Doe", "role": "Lead"}, {"name": "John Smith", "role": "Contributor"}], "tags": ["vaccination", "campaign", "2025"]}',
                '--variable', 'notes:null',
            ]
        )

        # Should complete successfully with valid data
        self.assertEqual(result.returncode, 0)

    def test_complex_success_with_invalid_data(self):
        """Test execution with data that causes pipeline to fail."""
        result = self._run_jpipe_runner(
            additional_args=[
                "--config-file", str(self.config_file),
                "--variable", 'settings: {}, "options": {}}',
            ],
            expected_exit_code=1
        )

        # Should fail because aggregated result (1*2=2) is not > 10
        self.assertEqual(result.returncode, 1)

    def test_complex_fail_with_empty_data(self):
        """Test execution with empty data that should fail validation."""
        result = self._run_jpipe_runner(
            expected_exit_code=1
        )

        # Should fail because no data to process
        self.assertEqual(result.returncode, 1)

    def test_complex_success_dry_run(self):
        """Test dry run mode to ensure no actual execution occurs."""
        result = self._run_jpipe_runner(additional_args=[
            "--config-file", str(self.config_file),
            "--dry-run"
        ])

        # Dry run should complete successfully, without any log errors
        self.assertFalse(result.stderr)
        self.assertEqual(result.returncode, 0)

    def test_complex_success_with_diagram_export(self):
        """Test diagram export functionality with complex success pipeline."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir)

            result = self._run_jpipe_runner(
                additional_args=[
                    "--config-file", str(self.config_file),
                    "--output-path", str(output_path),
                    "--format", "svg"
                ]
            )

            output_path = output_path / self.justification_name  # output svg same name as justification name

            # Check that diagram was generated
            expected_file = output_path.with_suffix(".svg")
            self.assertTrue(expected_file.exists(), f"Expected diagram file not found: {expected_file}")
            self.assertEqual(result.returncode, 0)

    def test_complex_success_validation_passes(self):
        """Test that the complex success justification passes validation."""
        result = self._run_jpipe_runner(additional_args=["--config-file", str(self.config_file)])

        # Should not contain any validation errors
        for validator in self.validators:
            self.assertNotIn(validator.lower(), result.stderr.lower(),
                             f"Validation error found for {validator}")
        self.assertEqual(result.returncode, 0)

    def test_complex_success_invalid_justification_fails(self):
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

            # Should fail with validation error
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(result.stderr, "Expected validation error not found in stderr")

        finally:
            os.unlink(invalid_file)

    def test_complex_success_missing_library_fails(self):
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

        # Should fail due to missing library
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
