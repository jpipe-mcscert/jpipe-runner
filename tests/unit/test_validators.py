import unittest
from unittest.mock import MagicMock, patch

import networkx as nx

from jpipe_runner.framework.context import RuntimeContext
from jpipe_runner.framework.validators import (
    BaseValidator,
    DuplicateProducerValidator,
    EvidenceDependencyValidator,
    JustificationSchemaValidator,
    MissingVariableValidator,
    OrderValidator,
    ProducedButNotConsumedValidator,
    SelfDependencyValidator,
    UnboundElementValidator,
)


class TestBaseValidator(unittest.TestCase):
    def test_validate_not_implemented(self):
        mock_pipeline = MagicMock()
        mock_ctx = MagicMock()
        validator = BaseValidator(mock_pipeline, mock_ctx)
        with self.assertRaises(NotImplementedError):
            validator.validate()


class TestMissingVariableValidator(unittest.TestCase):
    def test_missing_variable_detected(self):
        mock_ctx = MagicMock()
        mock_ctx._vars = {"func1": {RuntimeContext.CONSUME: {"var1": None}}}

        mock_pipeline = MagicMock()
        mock_pipeline.get_producer_key.return_value = None

        validator = MissingVariableValidator(mock_pipeline, mock_ctx)
        errors, _ = validator.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("missing variable", errors[0].lower())

    def test_no_error_when_variable_produced(self):
        mock_ctx = MagicMock()
        mock_ctx._vars = {"func1": {RuntimeContext.CONSUME: {"var1": None}}}

        mock_pipeline = MagicMock()
        mock_pipeline.get_producer_key.return_value = "func0"

        validator = MissingVariableValidator(mock_pipeline, mock_ctx)
        errors, _ = validator.validate()
        self.assertEqual(errors, [])


class TestSelfDependencyValidator(unittest.TestCase):
    def test_self_dependency_detected(self):
        mock_ctx = MagicMock()
        mock_ctx._vars = {"func1": {RuntimeContext.CONSUME: {"var1": None}}}

        mock_pipeline = MagicMock()
        mock_pipeline.get_producer_key.return_value = "func1"

        validator = SelfDependencyValidator(mock_pipeline, mock_ctx)
        errors, _ = validator.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("self-dependency", errors[0].lower())

    def test_no_self_dependency(self):
        mock_ctx = MagicMock()
        mock_ctx._vars = {"func1": {RuntimeContext.CONSUME: {"var1": None}}}

        mock_pipeline = MagicMock()
        mock_pipeline.get_producer_key.return_value = "func0"

        validator = SelfDependencyValidator(mock_pipeline, mock_ctx)
        errors, _ = validator.validate()
        self.assertEqual(errors, [])


class TestOrderValidator(unittest.TestCase):
    def test_self_dependency_in_order(self):
        mock_ctx = MagicMock()
        mock_ctx._vars = {"func1": {RuntimeContext.CONSUME: {"var1": None}}}

        mock_pipeline = MagicMock()
        mock_pipeline.get_execution_order.return_value = ["func1"]
        mock_pipeline.get_producer_key.return_value = "func1"

        validator = OrderValidator(mock_pipeline, mock_ctx)
        errors, _ = validator.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("self-dependency", errors[0].lower())

    def test_order_violation(self):
        mock_ctx = MagicMock()
        mock_ctx._vars = {"func1": {RuntimeContext.CONSUME: {"var1": None}}}

        mock_pipeline = MagicMock()
        mock_pipeline.get_execution_order.return_value = ["func1", "func2"]
        mock_pipeline.get_producer_key.return_value = "func2"

        validator = OrderValidator(mock_pipeline, mock_ctx)
        errors, _ = validator.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("execution order violation", errors[0].lower())

    def test_valid_order(self):
        mock_ctx = MagicMock()
        mock_ctx._vars = {"func2": {RuntimeContext.CONSUME: {"var1": None}}}

        mock_pipeline = MagicMock()
        mock_pipeline.get_execution_order.return_value = ["func1", "func2"]
        mock_pipeline.get_producer_key.return_value = "func1"

        validator = OrderValidator(mock_pipeline, mock_ctx)
        errors, _ = validator.validate()
        self.assertEqual(errors, [])


class TestProducedButNotConsumedValidator(unittest.TestCase):
    def setUp(self):
        patcher = patch("jpipe_runner.framework.logger.GLOBAL_LOGGER")
        self.addCleanup(patcher.stop)
        self.mock_logger = patcher.start()

        self.pipeline = MagicMock()
        self.mock_ctx = MagicMock()

    def test_no_produced_variables(self):
        self.mock_ctx._vars = {}
        validator = ProducedButNotConsumedValidator(self.pipeline, self.mock_ctx)
        errors, _ = validator.validate()
        self.assertEqual(errors, [])

    def test_produced_and_consumed_variable(self):
        self.mock_ctx._vars = {
            "func1": {
                RuntimeContext.PRODUCE: {"var1": None},
                RuntimeContext.CONSUME: {},
            },
            "func2": {
                RuntimeContext.PRODUCE: {},
                RuntimeContext.CONSUME: {"var1": None},
            },
        }
        validator = ProducedButNotConsumedValidator(self.pipeline, self.mock_ctx)
        errors, _ = validator.validate()
        self.assertEqual(errors, [])

    def test_produced_but_not_consumed_variable(self):
        self.mock_ctx._vars = {
            "func1": {
                RuntimeContext.PRODUCE: {"var1": None},
                RuntimeContext.CONSUME: {},
            },
            "func2": {
                RuntimeContext.PRODUCE: {},
                RuntimeContext.CONSUME: {},
            },
        }
        validator = ProducedButNotConsumedValidator(self.pipeline, self.mock_ctx)
        _, warnings = validator.validate()
        self.assertEqual(len(warnings), 1)
        self.assertIn("produced variable not consumed", warnings[0].lower())
        self.assertIn("var1", warnings[0])
        self.assertIn("func1", warnings[0])


class TestDuplicateProducerValidator(unittest.TestCase):
    def setUp(self):
        # Patch ctx globally where DuplicateProducerValidator is defined
        patcher = patch("jpipe_runner.framework.context.ctx")
        self.mock_ctx = patcher.start()
        self.addCleanup(patcher.stop)

        # Create a fake pipeline object
        self.mock_pipeline = MagicMock()
        self.validator = DuplicateProducerValidator(pipeline=self.mock_pipeline, ctx=self.mock_ctx)

    def test_no_duplicate_producers(self):
        # Simulate context: one function produces 'x', another produces 'y'
        self.mock_ctx._vars = {
            "func_a": {RuntimeContext.PRODUCE: {"x": None}},
            "func_b": {RuntimeContext.PRODUCE: {"y": None}},
        }

        errors, _ = self.validator.validate()
        self.assertEqual(errors, [])

    def test_single_duplicate_variable(self):
        # Simulate two functions producing 'x'
        self.mock_ctx._vars = {
            "func_a": {RuntimeContext.PRODUCE: {"x": None}},
            "func_b": {RuntimeContext.PRODUCE: {"x": None}},
        }

        errors, _ = self.validator.validate()
        self.assertEqual(len(errors), 1)
        self.assertIn("Variable 'x' is produced by multiple functions", errors[0])
        self.assertIn("func_a", errors[0])
        self.assertIn("func_b", errors[0])

    def test_multiple_duplicates(self):
        # Simulate multiple variables with duplicate producers
        self.mock_ctx._vars = {
            "func_a": {RuntimeContext.PRODUCE: {"x": None, "y": None}},
            "func_b": {RuntimeContext.PRODUCE: {"y": None, "z": None}},
            "func_c": {RuntimeContext.PRODUCE: {"x": None}},
        }

        errors, _ = self.validator.validate()
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("Variable 'x'" in e for e in errors))
        self.assertTrue(any("Variable 'y'" in e for e in errors))

    def test_empty_context(self):
        self.mock_ctx._vars = {}

        errors, _ = self.validator.validate()
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
            "relations": [{"source": "notebook", "target": "pep8"}],
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
                self.assertIn("is a required property", str(context.exception))

    def test_invalid_element_type_raises(self):
        data = self.valid_justification.copy()
        data["elements"] = [{"id": "e1", "label": "invalid", "type": "banana"}]
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertIn("'banana' is not one of", str(context.exception))

    def test_duplicate_element_ids_raises(self):
        data = self.valid_justification.copy()
        data["elements"] = [
            {"id": "dup", "label": "First", "type": "evidence"},
            {"id": "dup", "label": "Duplicate", "type": "strategy"},
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
        self.assertIn("'type' is a required property", str(context.exception))

    def test_non_list_elements_raises(self):
        data = self.valid_justification.copy()
        data["elements"] = "not a list"
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertIn("is not of type 'array'", str(context.exception))

    def test_non_list_relations_raises(self):
        data = self.valid_justification.copy()
        data["relations"] = "not a list"
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertIn("is not of type 'array'", str(context.exception))

    def test_relation_missing_keys_raises(self):
        data = self.valid_justification.copy()
        data["relations"] = [{"source": "notebook"}]  # Missing target
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertIn("'target' is a required property", str(context.exception))

    def test_relation_with_unknown_id_raises(self):
        data = self.valid_justification.copy()
        data["relations"] = [{"source": "unknown_id", "target": "pep8"}]
        validator = JustificationSchemaValidator(data)
        with self.assertRaises(ValueError) as context:
            validator.validate()
        self.assertEqual(
            str(context.exception), "Relation 0 refers to unknown source id 'unknown_id'"
        )


    def test_optional_escaped_field_is_allowed(self):
        data = {
            **self.valid_justification,
            "elements": [{"id": "e1", "label": "L", "type": "evidence", "escaped": "l"}],
            "relations": [],
        }
        try:
            JustificationSchemaValidator(data).validate()
        except Exception as e:
            self.fail(f"escaped field raised unexpected exception: {e}")

    def test_invalid_top_level_type_raises(self):
        data = {**self.valid_justification, "type": "not_justification"}
        with self.assertRaises(ValueError) as context:
            JustificationSchemaValidator(data).validate()
        self.assertIn("is not one of", str(context.exception))

    def test_extra_element_fields_are_allowed(self):
        data = {
            **self.valid_justification,
            "elements": [{"id": "e1", "label": "L", "type": "evidence", "extra": "ok"}],
            "relations": [],
        }
        try:
            JustificationSchemaValidator(data).validate()
        except Exception as e:
            self.fail(f"extra element field raised unexpected exception: {e}")


def _make_graph(*nodes):
    """Helper: build a DiGraph from (node_id, type, fn_name, label) tuples plus optional edges."""
    g = nx.DiGraph()
    for item in nodes:
        if isinstance(item, tuple) and len(item) == 4:
            nid, ntype, fn, label = item
            g.add_node(nid, type=ntype, function_name=fn, label=label)
        elif isinstance(item, tuple) and len(item) == 2:
            g.add_edge(*item)
    return g


class TestEvidenceDependencyValidator(unittest.TestCase):
    def _make_pipeline(self, graph):
        p = MagicMock()
        p.graph = graph
        return p

    def _make_ctx(self, vars_dict):
        c = MagicMock()
        c._vars = vars_dict
        return c

    def test_evidence_no_produce_raises_error(self):
        g = nx.DiGraph()
        g.add_node("E1", type="evidence", function_name="check_file", label="Check file")
        g.add_node("S1", type="strategy", function_name="process", label="Process")
        g.add_edge("E1", "S1")

        ctx = self._make_ctx({"check_file": {RuntimeContext.PRODUCE: {}}})
        v = EvidenceDependencyValidator(self._make_pipeline(g), ctx, g)
        errors, _ = v.validate()

        self.assertEqual(len(errors), 1)
        self.assertIn("E1", errors[0])
        self.assertIn("Check file", errors[0])

    def test_evidence_produces_and_strategy_consumes_passes(self):
        g = nx.DiGraph()
        g.add_node("E1", type="evidence", function_name="check_file", label="Check file")
        g.add_node("S1", type="strategy", function_name="process", label="Process")
        g.add_edge("E1", "S1")

        ctx = self._make_ctx({
            "check_file": {RuntimeContext.PRODUCE: {"file_exists": True}},
            "process": {RuntimeContext.CONSUME: {"file_exists": None}},
        })
        v = EvidenceDependencyValidator(self._make_pipeline(g), ctx, g)
        errors, _ = v.validate()
        self.assertEqual(errors, [])

    def test_strategy_missing_consumption_of_evidence_var(self):
        g = nx.DiGraph()
        g.add_node("E1", type="evidence", function_name="gen", label="Gen")
        g.add_node("S1", type="strategy", function_name="process", label="Process")
        g.add_edge("E1", "S1")

        ctx = self._make_ctx({
            "gen": {RuntimeContext.PRODUCE: {"file_exists": True}},
            "process": {RuntimeContext.CONSUME: {"other_var": None}},
        })
        v = EvidenceDependencyValidator(self._make_pipeline(g), ctx, g)
        errors, _ = v.validate()

        self.assertEqual(len(errors), 1)
        self.assertIn("E1", errors[0])
        self.assertIn("process", errors[0])

    def test_sub_conclusion_bound_predecessor_is_checked(self):
        g = nx.DiGraph()
        g.add_node("SC1", type="sub-conclusion", function_name="sub_fn", label="Sub")
        g.add_node("S1", type="strategy", function_name="strat_fn", label="Strategy")
        g.add_edge("SC1", "S1")

        ctx = self._make_ctx({
            "sub_fn": {RuntimeContext.PRODUCE: {"sub_result": True}},
            "strat_fn": {RuntimeContext.CONSUME: {"other": None}},
        })
        v = EvidenceDependencyValidator(self._make_pipeline(g), ctx, g)
        errors, _ = v.validate()

        self.assertEqual(len(errors), 1)
        self.assertIn("SC1", errors[0])

    def test_sub_conclusion_without_ctx_entry_is_skipped(self):
        g = nx.DiGraph()
        g.add_node("SC1", type="sub-conclusion", function_name="sub_fn", label="Sub")
        g.add_node("S1", type="strategy", function_name="strat_fn", label="Strategy")
        g.add_edge("SC1", "S1")

        # ctx has no entry for "sub_fn" → dict.get() returns None → sub-conclusion skipped
        ctx = self._make_ctx({"strat_fn": {RuntimeContext.CONSUME: {}}})
        v = EvidenceDependencyValidator(self._make_pipeline(g), ctx, g)
        errors, _ = v.validate()
        self.assertEqual(errors, [])


class TestUnboundElementValidator(unittest.TestCase):
    def _make_pipeline(self, graph, name="test_pipeline"):
        p = MagicMock()
        p.graph = graph
        p.justification_name = name
        return p

    def test_unbound_evidence_raises_error(self):
        g = nx.DiGraph()
        g.add_node("E1", type="evidence", function_name="fn", label="Evidence")

        v = UnboundElementValidator(self._make_pipeline(g), MagicMock(), registry={})
        errors, _ = v.validate()

        self.assertEqual(len(errors), 1)
        self.assertIn("E1", errors[0])
        self.assertIn("unbound", errors[0].lower())

    def test_unbound_strategy_raises_error(self):
        g = nx.DiGraph()
        g.add_node("S1", type="strategy", function_name="fn", label="Strategy")

        v = UnboundElementValidator(self._make_pipeline(g), MagicMock(), registry={})
        errors, _ = v.validate()

        self.assertEqual(len(errors), 1)
        self.assertIn("S1", errors[0])

    def test_conclusion_not_checked(self):
        g = nx.DiGraph()
        g.add_node("C1", type="conclusion", function_name="fn", label="Conclusion")

        v = UnboundElementValidator(self._make_pipeline(g), MagicMock(), registry={})
        errors, _ = v.validate()
        self.assertEqual(errors, [])

    def test_sub_conclusion_not_checked(self):
        g = nx.DiGraph()
        g.add_node("SC1", type="sub-conclusion", function_name="fn", label="Sub")

        v = UnboundElementValidator(self._make_pipeline(g), MagicMock(), registry={})
        errors, _ = v.validate()
        self.assertEqual(errors, [])

    def test_bound_by_plain_id_passes(self):
        g = nx.DiGraph()
        g.add_node("E1", type="evidence", function_name="fn", label="Evidence")

        v = UnboundElementValidator(
            self._make_pipeline(g), MagicMock(), registry={"E1": "fn"}
        )
        errors, _ = v.validate()
        self.assertEqual(errors, [])

    def test_bound_by_qualified_id_passes(self):
        g = nx.DiGraph()
        g.add_node("E1", type="evidence", function_name="fn", label="Evidence")

        v = UnboundElementValidator(
            self._make_pipeline(g, name="my_pipeline"),
            MagicMock(),
            registry={"my_pipeline:E1": "fn"},
        )
        errors, _ = v.validate()
        self.assertEqual(errors, [])

    def test_multiple_nodes_some_bound(self):
        g = nx.DiGraph()
        g.add_node("E1", type="evidence", function_name="fn1", label="Ev1")
        g.add_node("S1", type="strategy", function_name="fn2", label="St1")
        g.add_node("C1", type="conclusion", function_name="fn3", label="Con")

        v = UnboundElementValidator(
            self._make_pipeline(g), MagicMock(), registry={"E1": "fn1"}
        )
        errors, _ = v.validate()

        # S1 is unbound, C1 is not checked
        self.assertEqual(len(errors), 1)
        self.assertIn("S1", errors[0])


if __name__ == "__main__":
    unittest.main()
