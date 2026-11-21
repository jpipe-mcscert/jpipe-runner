"""The per-run value store, and the absence of state that outlives a run (ADR-0009)."""

import ast

import pytest

from jpipe_runner.values import UNSET, ProducedValue, ValueStore
from tests.conftest import REPO_ROOT

PACKAGE = REPO_ROOT / "src" / "jpipe_runner"
PER_RUN = {"ValueStore", "StepRegistry"}


def test_a_produced_value_carries_its_producer() -> None:
    store = ValueStore()
    store.put("coverage", 92.0, produced_by="m:e")
    assert store.get("coverage", "m:e") == 92.0
    assert store.producers("coverage") == ("m:e",)
    assert "coverage" in store


def test_a_variable_nothing_produced_is_unset() -> None:
    store = ValueStore()
    assert store.get("coverage", "m:e") is UNSET
    assert store.producers("coverage") == ()
    assert "coverage" not in store


def test_unset_is_not_none() -> None:
    store = ValueStore()
    store.put("result", None, produced_by="m:s")
    assert store.get("result", "m:s") is None
    assert store.get("result", "m:s") is not UNSET
    assert store.producers("result") == ("m:s",)


def test_unset_is_false_and_reads_as_its_name() -> None:
    assert not UNSET
    assert repr(UNSET) == "UNSET"


def test_two_producers_of_one_variable_each_keep_their_value() -> None:
    store = ValueStore()
    store.put("coverage", 92.0, produced_by="m:a:e")
    store.put("coverage", 50.0, produced_by="m:b:e")
    assert store.get("coverage", "m:a:e") == 92.0
    assert store.get("coverage", "m:b:e") == 50.0
    assert store.get("coverage", "m:c:e") is UNSET
    assert store.producers("coverage") == ("m:a:e", "m:b:e")


def test_a_producer_produces_a_variable_once() -> None:
    store = ValueStore()
    store.put("coverage", 92.0, produced_by="m:e1")
    with pytest.raises(ValueError, match="m:e1"):
        store.put("coverage", 50.0, produced_by="m:e1")
    assert store.get("coverage", "m:e1") == 92.0


def test_values_are_listed_in_the_order_produced() -> None:
    store = ValueStore()
    store.put("b", 2, produced_by="m:e2")
    store.put("a", 1, produced_by="m:e1")
    store.put("b", 3, produced_by="m:e3")
    assert list(store.entries()) == [
        ("b", ProducedValue(2, "m:e2")),
        ("a", ProducedValue(1, "m:e1")),
        ("b", ProducedValue(3, "m:e3")),
    ]
    assert len(store) == 3
    assert repr(store) == "ValueStore(3 values)"


def test_two_runs_do_not_share_values() -> None:
    first, second = ValueStore(), ValueStore()
    first.put("coverage", 92.0, produced_by="m:e")
    assert second.get("coverage", "m:e") is UNSET
    second.put("coverage", 50.0, produced_by="m:e")
    assert first.get("coverage", "m:e") == 92.0


def _module_level_statements() -> list[tuple[str, ast.stmt]]:
    return [
        (path.relative_to(PACKAGE).as_posix(), statement)
        for path in sorted(PACKAGE.rglob("*.py"))
        for statement in ast.parse(path.read_text(encoding="utf-8")).body
    ]


def _calls(node: ast.AST) -> set[str]:
    names = set()
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
        function = call.func
        while isinstance(function, ast.Attribute):
            function = function.value
        if isinstance(function, ast.Name):
            names.add(function.id)
    return names


@pytest.mark.parametrize(
    ("module", "statement"),
    [
        pytest.param(module, statement, id=f"{module}:{statement.lineno}")
        for module, statement in _module_level_statements()
        if isinstance(statement, ast.Assign | ast.AnnAssign)
    ],
)
def test_no_module_holds_state_of_a_run(module: str, statement: ast.stmt) -> None:
    assert _calls(statement) & PER_RUN == set(), f"{module} builds a {PER_RUN} at import"


def test_no_function_rebinds_module_state() -> None:
    offenders = [
        f"{path.relative_to(PACKAGE)}:{node.lineno}"
        for path in sorted(PACKAGE.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Global | ast.Nonlocal)
    ]
    assert offenders == []
