import unittest
from unittest.mock import MagicMock, patch

from jpipe_runner.framework.context import RuntimeContext
from jpipe_runner.framework.validators import (
    BaseValidator,
    MissingVariableValidator,
    SelfDependencyValidator,
    OrderValidator
)


class TestBaseValidator(unittest.TestCase):
    def test_validate_not_implemented(self):
        mock_pipeline = MagicMock()
        validator = BaseValidator(mock_pipeline)
        with self.assertRaises(NotImplementedError):
            validator.validate()


class TestMissingVariableValidator(unittest.TestCase):
    @patch("jpipe_runner.framework.validators.ctx")
    def test_missing_variable_detected(self, mock_ctx):
        mock_ctx._vars = {
            "func1": {
                RuntimeContext.CONSUME: {"var1": None}
            }
        }

        mock_pipeline = MagicMock()
        mock_pipeline.get_producer_key.return_value = None

        validator = MissingVariableValidator(mock_pipeline)
        errors = validator.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("missing variable", errors[0])

    @patch("jpipe_runner.framework.validators.ctx")
    def test_no_error_when_variable_produced(self, mock_ctx):
        mock_ctx._vars = {
            "func1": {
                RuntimeContext.CONSUME: {"var1": None}
            }
        }

        mock_pipeline = MagicMock()
        mock_pipeline.get_producer_key.return_value = "func0"

        validator = MissingVariableValidator(mock_pipeline)
        errors = validator.validate()
        self.assertEqual(errors, [])


class TestSelfDependencyValidator(unittest.TestCase):
    @patch("jpipe_runner.framework.validators.ctx")
    def test_self_dependency_detected(self, mock_ctx):
        mock_ctx._vars = {
            "func1": {
                RuntimeContext.CONSUME: {"var1": None}
            }
        }

        mock_pipeline = MagicMock()
        mock_pipeline.get_producer_key.return_value = "func1"

        validator = SelfDependencyValidator(mock_pipeline)
        errors = validator.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("self-dependency", errors[0])

    @patch("jpipe_runner.framework.validators.ctx")
    def test_no_self_dependency(self, mock_ctx):
        mock_ctx._vars = {
            "func1": {
                RuntimeContext.CONSUME: {"var1": None}
            }
        }

        mock_pipeline = MagicMock()
        mock_pipeline.get_producer_key.return_value = "func0"

        validator = SelfDependencyValidator(mock_pipeline)
        errors = validator.validate()
        self.assertEqual(errors, [])


class TestOrderValidator(unittest.TestCase):
    @patch("jpipe_runner.framework.validators.ctx")
    def test_self_dependency_in_order(self, mock_ctx):
        mock_ctx._vars = {
            "func1": {
                RuntimeContext.CONSUME: {"var1": None}
            }
        }

        mock_pipeline = MagicMock()
        mock_pipeline.get_execution_order.return_value = ["func1"]
        mock_pipeline.get_producer_key.return_value = "func1"

        validator = OrderValidator(mock_pipeline)
        errors = validator.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("self-dependency", errors[0])

    @patch("jpipe_runner.framework.validators.ctx")
    def test_order_violation(self, mock_ctx):
        mock_ctx._vars = {
            "func1": {
                RuntimeContext.CONSUME: {"var1": None}
            }
        }

        mock_pipeline = MagicMock()
        mock_pipeline.get_execution_order.return_value = ["func1", "func2"]
        mock_pipeline.get_producer_key.return_value = "func2"

        validator = OrderValidator(mock_pipeline)
        errors = validator.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("execution order violation", errors[0].lower())

    @patch("jpipe_runner.framework.validators.ctx")
    def test_valid_order(self, mock_ctx):
        mock_ctx._vars = {
            "func2": {
                RuntimeContext.CONSUME: {"var1": None}
            }
        }

        mock_pipeline = MagicMock()
        mock_pipeline.get_execution_order.return_value = ["func1", "func2"]
        mock_pipeline.get_producer_key.return_value = "func1"

        validator = OrderValidator(mock_pipeline)
        errors = validator.validate()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
