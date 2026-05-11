import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TestSimpleImportSuccessE2E(unittest.TestCase):
    """
    End-to-end tests for simple import success pipeline.
    """

    def setUp(self):
        self.test_dir = Path(__file__).parent / "resources" / "simple_import_success"
        self.justification_file = self.test_dir / "file_validation.json"
        self.config_file = self.test_dir / "config.yaml"
        self.python_file = self.test_dir / "steps" / "file_validation.py"
        self.justification_name = "file_validation"
        self.assertTrue(
            self.justification_file.exists(),
            f"Justification file not found: {self.justification_file}",
        )
        self.assertTrue(self.config_file.exists(), f"Config file not found: {self.config_file}")
        self.assertTrue(self.python_file.exists(), f"Python file not found: {self.python_file}")

    def _run_jpipe_runner(self, additional_args=None, expected_exit_code=0):
        cmd = [
            sys.executable,
            "-m",
            "jpipe_runner.runner",
            "--library",
            str(self.python_file),
            "--python-path",
            str(self.test_dir),
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

    def test_simple_import_success_normal_execution(self):
        """
        Test pipeline with a file that exists.
        """
        result = self._run_jpipe_runner(additional_args=["--config-file", str(self.config_file)])
        self.assertIn(self.justification_name, result.stdout.lower())
        self.assertEqual(result.returncode, 0)

    def test_simple_import_success_with_diagram_export(self):
        """
        Test diagram export functionality with simple import success pipeline.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir)

            result = self._run_jpipe_runner(
                additional_args=[
                    "--config-file",
                    str(self.config_file),
                    "--output-path",
                    str(output_path),
                    "--format",
                    "svg",
                ]
            )

            output_path = (
                output_path / self.justification_name
            )  # output svg same name as justification name

            # Check that diagram was generated
            expected_file = output_path.with_suffix(".svg")
            self.assertTrue(
                expected_file.exists(), f"Expected diagram file not found: {expected_file}"
            )
            self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
