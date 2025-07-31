import json
from typing import Iterable
from unittest.mock import patch, MagicMock

import networkx as nx
import pytest

from jpipe_runner.enums import StatusType
from jpipe_runner.exceptions import FunctionException
from jpipe_runner.framework.context import RuntimeContext, ctx
from jpipe_runner.framework.engine import PipelineEngine


@pytest.fixture
def sample_justification(tmp_path):
    data = {
        "name": "Test Justification",
        "elements": [
            {"id": "node1", "type": "evidence", "label": "Node 1"},
            {"id": "node2", "type": "strategy", "label": "Node 2"},
            {"id": "node3", "type": "conclusion", "label": "Node 3"},
        ],
        "relations": [
            {"source": "node1", "target": "node2"},
            {"source": "node2", "target": "node3"},
        ],
        "type": "justification",
    }
    path = tmp_path / "justification.json"
    path.write_text(json.dumps(data))
    return str(path)


@pytest.fixture
def sample_config(tmp_path):
    content = """
    var1: value1
    var2: value2
    """
    path = tmp_path / "config.yaml"
    path.write_text(content)
    return str(path)


def test_init_without_config_with_variables(sample_justification):
    # Should initialize and parse justification with no config path
    with patch("jpipe_runner.framework.engine.PipelineEngine.load_config") as mock_load_config:
        variables: Iterable[tuple[str, str]] | None = [("var1", "value1"), ("var2", "value2")]
        engine = PipelineEngine(None, sample_justification, mark_step=MagicMock(),
                                mark_substep=MagicMock(),
                                mark_node_as_graph=MagicMock(),
                                variables=variables)
        mock_load_config.assert_called_once_with(None, variables)
        assert isinstance(engine.graph, nx.DiGraph)
        assert engine.justification_name == "Test Justification"


def test_init_with_config(sample_config, sample_justification):
    with patch("jpipe_runner.framework.engine.PipelineEngine.load_config") as mock_load_config:
        engine = PipelineEngine(sample_config, sample_justification,
                                mark_step=MagicMock(),
                                mark_substep=MagicMock(),
                                mark_node_as_graph=MagicMock())
        mock_load_config.assert_called_once_with(sample_config, None)
        assert isinstance(engine.graph, nx.DiGraph)


def test_parse_justification_success(sample_justification):
    engine = PipelineEngine(None, sample_justification,
                            mark_step=MagicMock(),
                            mark_substep=MagicMock(),
                            mark_node_as_graph=MagicMock())
    graph = engine.parse_justification(sample_justification)
    assert isinstance(graph, nx.DiGraph)
    assert graph.number_of_nodes() == 3
    assert graph.number_of_edges() == 2


def test_parse_justification_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("invalid json")
    engine = PipelineEngine(None, path,
                            mark_step=MagicMock(),
                            mark_substep=MagicMock(),
                            mark_node_as_graph=MagicMock())
    graph = engine.parse_justification(str(path))
    assert isinstance(graph, nx.DiGraph)
    assert graph.number_of_nodes() == 0


def test_get_producer_key_found():
    engine = PipelineEngine(None, None,
                            mark_step=MagicMock(),
                            mark_substep=MagicMock(),
                            mark_node_as_graph=MagicMock())
    ctx._vars = {
        "funcA": {RuntimeContext.PRODUCE: {"varX": 123}},
        "funcB": {RuntimeContext.PRODUCE: {"varY": 456}},
    }
    key = engine.get_producer_key("varX")
    assert key == "funcA"
    key_none = engine.get_producer_key("varZ")
    assert key_none is None


def test_validate_all_passes(sample_justification):
    mock_validator = MagicMock()
    mock_validator.validate.return_value = []
    mock_validator.errors = []

    with patch("jpipe_runner.framework.engine.MissingVariableValidator", return_value=mock_validator), \
            patch("jpipe_runner.framework.engine.SelfDependencyValidator", return_value=mock_validator), \
            patch("jpipe_runner.framework.engine.OrderValidator", return_value=mock_validator), \
            patch("jpipe_runner.framework.engine.ProducedButNotConsumedValidator", return_value=mock_validator):
        engine = PipelineEngine(config_path=None, justification_path=None,
                                mark_step=MagicMock(),
                                mark_substep=MagicMock(),
                                mark_node_as_graph=MagicMock())
        engine.graph = MagicMock()

        assert engine.validate() is True


def test_validate_missing_variable_fails():
    mv_validator = MagicMock()
    mv_validator.validate.return_value = ["Missing variable error"]
    mv_validator.errors = ["Missing variable error"]

    sd_validator = MagicMock()
    sd_validator.validate.return_value = []
    sd_validator.errors = []

    o_validator = MagicMock()
    o_validator.validate.return_value = []
    o_validator.errors = []

    with patch("jpipe_runner.framework.engine.MissingVariableValidator", return_value=mv_validator), \
            patch("jpipe_runner.framework.engine.SelfDependencyValidator", return_value=sd_validator), \
            patch("jpipe_runner.framework.engine.OrderValidator", return_value=o_validator):
        engine = PipelineEngine(config_path=None, justification_path=None,
                                mark_step=MagicMock(),
                                mark_substep=MagicMock(),
                                mark_node_as_graph=MagicMock())
        engine.graph = MagicMock()

        assert engine.validate() is False


def test_validate_self_dependency_fails():
    mv_validator = MagicMock()
    mv_validator.validate.return_value = []
    mv_validator.errors = []

    sd_validator = MagicMock()
    sd_validator.validate.return_value = ["Self-dependency error"]
    sd_validator.errors = ["Self-dependency error"]

    o_validator = MagicMock()
    o_validator.validate.return_value = []
    o_validator.errors = []

    with patch("jpipe_runner.framework.engine.MissingVariableValidator", return_value=mv_validator), \
            patch("jpipe_runner.framework.engine.SelfDependencyValidator", return_value=sd_validator), \
            patch("jpipe_runner.framework.engine.OrderValidator", return_value=o_validator):
        engine = PipelineEngine(config_path=None, justification_path=None,
                                mark_step=MagicMock(),
                                mark_substep=MagicMock(),
                                mark_node_as_graph=MagicMock())
        engine.graph = MagicMock()

        assert engine.validate() is False


def test_validate_order_error():
    mv_validator = MagicMock()
    mv_validator.validate.return_value = []
    mv_validator.errors = []

    sd_validator = MagicMock()
    sd_validator.validate.return_value = []
    sd_validator.errors = []

    o_validator = MagicMock()
    o_validator.validate.return_value = ["Order error: A before B"]
    o_validator.errors = ["Order error: A before B"]

    with patch("jpipe_runner.framework.engine.MissingVariableValidator", return_value=mv_validator), \
            patch("jpipe_runner.framework.engine.SelfDependencyValidator", return_value=sd_validator), \
            patch("jpipe_runner.framework.engine.OrderValidator", return_value=o_validator):
        engine = PipelineEngine(config_path=None, justification_path=None,
                                mark_step=MagicMock(),
                                mark_substep=MagicMock(),
                                mark_node_as_graph=MagicMock())
        engine.graph = MagicMock()

        assert engine.validate() is False


def test_get_execution_order_valid_graph():
    # Arrange
    engine = PipelineEngine(config_path=None, justification_path=None,
                            mark_step=MagicMock(),
                            mark_substep=MagicMock(),
                            mark_node_as_graph=MagicMock())
    engine.graph = nx.DiGraph()
    engine.graph.add_edges_from([("A", "B"), ("B", "C")])

    # Act
    order = engine.get_execution_order()

    # Assert
    assert order == ["A", "B", "C"]


def test_get_execution_order_with_cycle_logs_error():
    # Arrange
    engine = PipelineEngine(config_path=None, justification_path=None,
                            mark_step=MagicMock(),
                            mark_substep=MagicMock(),
                            mark_node_as_graph=MagicMock())
    engine.graph = nx.DiGraph()
    engine.graph.add_edges_from([("A", "B"), ("B", "A")])  # cycle

    # Act
    order = engine.get_execution_order()

    # Assert
    assert order == []


def test_get_execution_order_and_cycle():
    engine = PipelineEngine(None, None,
                            mark_step=MagicMock(),
                            mark_substep=MagicMock(),
                            mark_node_as_graph=MagicMock())
    g = nx.DiGraph()
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    engine.graph = g
    order = engine.get_execution_order()
    assert order == ["a", "b", "c"]

    # Create cycle
    g.add_edge("c", "a")
    order = engine.get_execution_order()
    assert order == []


def test_justify_dry_run_and_normal(sample_justification):
    engine = PipelineEngine(None, sample_justification,
                            mark_step=MagicMock(),
                            mark_substep=MagicMock(),
                            mark_node_as_graph=MagicMock())
    engine.validate = MagicMock(return_value=True)

    # Mock execution order to control flow
    engine.get_execution_order = MagicMock(return_value=["node1", "node2", "node3"])

    # Setup runtime mock
    runtime = MagicMock()
    runtime.call_function = MagicMock(return_value=True)

    results = list(engine.justify(runtime, dry_run=True))
    for res in results:
        assert res["status"] == StatusType.PASS

    # Normal run with success
    results = list(engine.justify(runtime, dry_run=False))
    for res in results:
        assert res["status"] in {StatusType.PASS, StatusType.SKIP}

    # Simulate a failure in runtime.call_function
    runtime.call_function.side_effect = FunctionException("fail")
    results = list(engine.justify(runtime, dry_run=False))
    # At least one should fail
    assert any(r["status"] == StatusType.FAIL for r in results)


if __name__ == '__main__':
    pytest.main([__file__])
