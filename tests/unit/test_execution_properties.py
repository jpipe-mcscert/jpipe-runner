"""Properties of the topological order and of execution, over generated models (layer 3).

The order is checked against Kahn's algorithm taking the first ready element in model
order. Execution is checked against an oracle stated with ``upstream`` alone, without the
engine's propagation: an element is *reached* when every element upstream of it passes
on its own account (its step passes, or it is an unbound claim); a reached element has
its own status and a bound one is called; an element not reached is skipped, blocked by
the reached elements upstream of it that did not pass.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jpipe_runner import (
    Fail,
    Outcome,
    Pass,
    Skip,
    conclusion,
    evidence,
    loader,
    strategy,
    sub_conclusion,
)
from jpipe_runner.engine import Status, Verdict, run
from jpipe_runner.model import Element, Justification, Kind
from jpipe_runner.steps import StepRegistry, step_of
from tests.strategies import FAIL, PASS, RAISE, SKIP, justifications, step_plans

Plan = dict[str, str | None]
Calls = list[tuple[str, dict[str, Any]]]

OWN_STATUS = {PASS: Status.PASS, FAIL: Status.FAIL, SKIP: Status.SKIP, RAISE: Status.FAIL}
OBSERVED = "log.txt"


def _load(model: dict[str, Any]) -> Justification:
    return loader.loads(json.dumps(model))


models = justifications().map(_load)
planned = justifications().flatmap(lambda model: st.tuples(st.just(model), step_plans(model)))


# --- The topological order -----------------------------------------------------------------


def _kahn_in_model_order(justification: Justification) -> list[str]:
    waiting = {e.id: len(justification.supporters(e.id)) for e in justification}
    order: list[str] = []
    while len(order) < len(justification):
        ready = next(e for e in justification if waiting[e.id] == 0 and e.id not in order)
        order.append(ready.id)
        for supported in justification.supported(ready.id):
            waiting[supported.id] -= 1
    return order


@given(models)
def test_the_order_is_every_element_once_supporters_first(justification: Justification) -> None:
    order = [element.id for element in justification.topological_order()]
    position = {element_id: index for index, element_id in enumerate(order)}
    assert sorted(order) == sorted(element.id for element in justification)
    for relation in justification.relations:
        assert position[relation.source] < position[relation.target]
    for element in justification:
        for supporter in justification.upstream(element.id):
            assert position[supporter.id] < position[element.id]


@given(models)
def test_the_order_breaks_ties_by_model_order(justification: Justification) -> None:
    assert [e.id for e in justification.topological_order()] == _kahn_in_model_order(justification)


@given(justifications())
def test_the_order_does_not_depend_on_how_relations_are_listed(model: dict[str, Any]) -> None:
    reversed_relations = {**model, "relations": list(reversed(model["relations"]))}
    assert _load(model).topological_order() == _load(reversed_relations).topological_order()


# --- Execution -----------------------------------------------------------------------------


def _variable(justification: Justification, element: Element) -> str:
    """The variable an evidence produces: one per evidence, named by its rank."""
    return f"v{justification.elements.index(element)}"


def _behave(
    element_id: str, behaviour: str, produces: list[str], calls: Calls
) -> Callable[..., Outcome]:
    def step(**arguments: Any) -> Outcome:
        calls.append((element_id, arguments))
        if behaviour == RAISE:
            raise RuntimeError(element_id)
        if behaviour == FAIL:
            return Fail(element_id)
        if behaviour == SKIP:
            return Skip(element_id)
        return Pass({name: element_id for name in produces})

    return step


def _library(justification: Justification, plan: Plan, calls: Calls) -> StepRegistry:
    """Each evidence produces a variable, which each strategy it supports consumes."""
    steps = []
    for element in justification:
        behaviour = plan[element.id]
        if behaviour is None:
            continue
        if element.kind is Kind.EVIDENCE:
            produces = [_variable(justification, element)]
            declare = evidence(element.id, observes={"log": OBSERVED}, produces=produces)
        elif element.kind is Kind.STRATEGY:
            produces = []
            consumed = [
                _variable(justification, supporter)
                for supporter in justification.supporters(element.id)
                if supporter.kind is Kind.EVIDENCE
            ]
            declare = strategy(element.id, consumes=consumed)
        else:
            produces = []
            claim = sub_conclusion if element.kind is Kind.SUB_CONCLUSION else conclusion
            declare = claim(element.id)
        steps.append(step_of(declare(_behave(element.id, behaviour, produces, calls))))
    return StepRegistry(step for step in steps if step is not None)


def _passes_alone(element: Element, plan: Plan) -> bool:
    return plan[element.id] in (PASS, None)


def _reached(justification: Justification, element: Element, plan: Plan) -> bool:
    return all(_passes_alone(u, plan) for u in justification.upstream(element.id))


def _expected(
    justification: Justification, plan: Plan
) -> dict[str, tuple[Status, tuple[str, ...]]]:
    expected = {}
    for element in justification:
        if _reached(justification, element, plan):
            behaviour = plan[element.id]
            expected[element.id] = (Status.PASS if behaviour is None else OWN_STATUS[behaviour], ())
        else:
            blocked = tuple(
                u.id
                for u in justification.upstream(element.id)
                if _reached(justification, u, plan) and not _passes_alone(u, plan)
            )
            expected[element.id] = (Status.SKIP, blocked)
    return expected


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("observed")
    (directory / OBSERVED).write_text("observed", encoding="utf-8")
    return directory


@given(planned)
def test_a_run_matches_the_oracle(root: Path, drawn: tuple[dict[str, Any], Plan]) -> None:
    model, plan = drawn
    justification = _load(model)
    calls: Calls = []

    result = run(justification, _library(justification, plan, calls), root=root)

    assert result.validation.passed, result.validation.errors
    expected = _expected(justification, plan)
    assert {r.element.id: (r.status, r.blocked_by) for r in result} == expected
    assert [r.element.id for r in result] == [e.id for e in justification.topological_order()]


@given(planned)
def test_steps_are_called_once_supporters_first_and_only_when_reached(
    root: Path, drawn: tuple[dict[str, Any], Plan]
) -> None:
    model, plan = drawn
    justification = _load(model)
    calls: Calls = []

    run(justification, _library(justification, plan, calls), root=root)

    called = [element_id for element_id, _ in calls]
    assert called == [
        element.id
        for element in justification.topological_order()
        if plan[element.id] is not None and _reached(justification, element, plan)
    ]


@given(planned)
def test_a_strategy_receives_what_its_evidence_produced(
    root: Path, drawn: tuple[dict[str, Any], Plan]
) -> None:
    model, plan = drawn
    justification = _load(model)
    calls: Calls = []

    run(justification, _library(justification, plan, calls), root=root)

    for element_id, arguments in calls:
        if justification.element(element_id).kind is Kind.STRATEGY:
            assert arguments == {
                _variable(justification, supporter): supporter.id
                for supporter in justification.supporters(element_id)
                if supporter.kind is Kind.EVIDENCE
            }


@given(planned)
def test_the_verdict_is_the_worst_status(root: Path, drawn: tuple[dict[str, Any], Plan]) -> None:
    model, plan = drawn
    justification = _load(model)

    result = run(justification, _library(justification, plan, []), root=root)

    statuses = {status for status, _ in _expected(justification, plan).values()}
    if Status.FAIL in statuses:
        assert result.verdict is Verdict.FAIL
    elif Status.SKIP in statuses:
        assert result.verdict is Verdict.SKIP
    else:
        assert result.verdict is Verdict.PASS
