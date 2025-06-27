import unittest
from unittest.mock import MagicMock, patch

from jpipe_runner.framework.context import RuntimeContext
from jpipe_runner.framework.validators import (
    BaseValidator,
    MissingVariableValidator,
    SelfDependencyValidator,
    OrderValidator, JustificationSchemaValidator
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


class TestJustificationSchemaValidator(unittest.TestCase):

    def setUp(self):
        self.valid_justification = {
            "name": "notebook_quality",
            "type": "justification",
            "elements": [
                {"id": "notebook", "label": "Notebook exists", "type": "evidence"},
                {"id": "pep8", "label": "PEP8 check", "type": "strategy"},
            ],
            "relations": [
                {"source": "notebook", "target": "pep8"}
            ]
        }

    def test_valid_justification_does_not_raise(self):
        validator = JustificationSchemaValidator(self.valid_justification)
        try:
            validator.validate()
        except Exception as e:
            self.fail(f"Validation raised an unexpected exception: {e}")

    def test_missing_top_level_keys_raises(self):
        for key in ["name", "type", "elements", "relations"]:
            with self.subTest(key=key):
                data = self.valid_justification.copy()
                del data[key]
                validator = JustificationSchemaValidator(data)
                with self.assertRaises(ValueError) as context:
                    validator.validate()
                self.assertIn("Missing top-level key(s)", str(context.exception))

    def test_invalid_element_type_raises(self):
        data = self.valid_justification.copy()
        data["elements"] = [{"id": "e1", "label": "invalid", "type": "banana"}]
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertEqual(str(context.exception), "Invalid type 'banana' in element 'e1'")

    def test_duplicate_element_ids_raises(self):
        data = self.valid_justification.copy()
        data["elements"] = [
            {"id": "dup", "label": "First", "type": "evidence"},
            {"id": "dup", "label": "Duplicate", "type": "strategy"}
        ]
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertEqual(str(context.exception), "Duplicate element id: 'dup'")

    def test_missing_element_keys_raises(self):
        data = self.valid_justification.copy()
        data["elements"] = [{"id": "e1", "label": "missing type"}]
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertIn("is missing required key 'type'", str(context.exception))

    def test_non_list_elements_raises(self):
        data = self.valid_justification.copy()
        data["elements"] = "not a list"
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertIn("'elements' must be a list", str(context.exception))

    def test_non_list_relations_raises(self):
        data = self.valid_justification.copy()
        data["relations"] = "not a list"
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertIn("'relations' must be a list", str(context.exception))

    def test_relation_missing_keys_raises(self):
        data = self.valid_justification.copy()
        data["relations"] = [{"source": "notebook"}]  # Missing target
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertIn("is missing required key 'target'", str(context.exception))

    def test_relation_with_unknown_id_raises(self):
        data = self.valid_justification.copy()
        data["relations"] = [{"source": "unknown_id", "target": "pep8"}]
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertEqual(str(context.exception), "Relation 0 refers to unknown source id 'unknown_id'")


if __name__ == "__main__":
    unittest.main()
