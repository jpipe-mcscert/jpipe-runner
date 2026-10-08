"""Binding resolution by example, including the cases v3 pinned (ADR-0007).

The rule's general properties are tested in test_binding_properties.py.
"""

from collections.abc import Callable

import pytest

from jpipe_runner import Outcome, Pass, conclusion, evidence, loader, strategy
from jpipe_runner.binding import (
    AMBIGUOUS_BINDING,
    CONFLICTING_BINDING,
    UNKNOWN_BINDING_TARGET,
    AmbiguousIdError,
    Binding,
    BindingTable,
    Resolver,
)
from jpipe_runner.diagnostics import Severity
from jpipe_runner.model import Element, Justification, Kind, Relation
from jpipe_runner.steps import Step, StepRegistry, step_of
from tests.scenarios import SCENARIOS_ROOT, Scenario, discover

CONCLUSION = Element("C1", "Done", Kind.CONCLUSION)
SCENARIOS = discover()


def justification(*elements: Element, name: str = "rigor") -> Justification:
    relations = [Relation(element.id, CONCLUSION.id) for element in elements]
    return Justification(name, (*elements, CONCLUSION), relations)


def evidence_element(element_id: str, *aliases: str) -> Element:
    return Element(element_id, element_id, Kind.EVIDENCE, aliases)


METRIC = evidence_element("rigor:r17:e_metric")


@pytest.mark.parametrize(
    "designator",
    [
        pytest.param("rigor:r17:e_metric", id="exact"),
        pytest.param("r17:e_metric", id="two-segment suffix"),
        pytest.param("e_metric", id="one-segment suffix"),
        pytest.param("rigor:rigor:r17:e_metric", id="qualified"),
    ],
)
def test_an_id_designates_by_exact_qualified_or_suffix_match(designator: str) -> None:
    assert Resolver(justification(METRIC)).resolve(designator) is METRIC


@pytest.mark.parametrize(
    "designator",
    [
        pytest.param("r17", id="a middle segment"),
        pytest.param("metric", id="part of a segment"),
        pytest.param("rigor", id="the first segment"),
        pytest.param("x:rigor:r17:e_metric", id="longer than the id"),
        pytest.param("other:e_metric", id="another justification's qualifier"),
        pytest.param("", id="empty"),
    ],
)
def test_matching_is_on_whole_trailing_segments(designator: str) -> None:
    assert Resolver(justification(METRIC)).resolve(designator) is None


def test_a_bare_id_is_qualified_by_the_justification_name() -> None:
    e1 = evidence_element("E1")
    resolver = Resolver(justification(e1, name="test"))
    assert resolver.resolve("test:E1") is e1
    assert resolver.resolve("E1") is e1
    assert resolver.resolve("other_pipeline:E1") is None


def test_an_alias_designates_the_element_it_was_merged_into() -> None:
    unified = evidence_element("rigor:unified_0", "rigor:r17:e_metric", "rigor:r18:e")
    resolver = Resolver(justification(unified))
    assert resolver.resolve("rigor:r17:e_metric") is unified
    assert resolver.resolve("r18:e") is unified
    assert resolver.resolve("e_metric") is unified
    assert resolver.resolve("C1") is CONCLUSION


def test_an_exact_match_wins_over_a_suffix_match() -> None:
    short = evidence_element("e_metric")
    resolver = Resolver(justification(short, METRIC))
    assert resolver.resolve("e_metric") is short


@pytest.mark.parametrize(
    "elements",
    [
        pytest.param(
            (evidence_element("rigor:r17:e"), evidence_element("perf:r5:e")), id="through ids"
        ),
        pytest.param(
            (
                evidence_element("rigor:unified_0", "rigor:r17:e"),
                evidence_element("perf:unified_1", "perf:r5:e"),
            ),
            id="through aliases",
        ),
    ],
)
def test_a_suffix_of_two_elements_is_ambiguous(elements: tuple[Element, ...]) -> None:
    resolver = Resolver(justification(*elements))
    with pytest.raises(AmbiguousIdError) as raised:
        resolver.resolve("e")
    assert raised.value.candidates == elements
    assert raised.value.designator == "e"


def test_a_suffix_of_two_ids_of_one_element_is_not_ambiguous() -> None:
    unified = evidence_element("rigor:unified_0", "rigor:r17:e", "perf:r5:e")
    assert Resolver(justification(unified)).resolve("e") is unified


# --- BindingTable -----------------------------------------------------------------------


def registry(*functions: Callable[..., Outcome]) -> StepRegistry:
    steps = [step_of(function) for function in functions]
    return StepRegistry(step for step in steps if step is not None)


def declared(function: Callable[..., Outcome]) -> Step:
    step = step_of(function)
    assert step is not None
    return step


@evidence("e_metric")
def report_metrics() -> Outcome:
    return Pass()


@evidence("rigor:r17:e_metric", "r17:e_metric")
def report_metrics_twice() -> Outcome:
    return Pass()


@conclusion("C1")
def done() -> Outcome:
    return Pass()


def codes(table: BindingTable) -> list[tuple[str, str | None]]:
    assert all(d.severity is Severity.ERROR for d in table.diagnostics)
    return [(d.code, d.element) for d in table.diagnostics]


def test_each_bound_element_has_its_step_in_model_order() -> None:
    table = BindingTable(justification(METRIC), registry(done, report_metrics))
    assert table.bindings == (
        Binding(METRIC, declared(report_metrics), ("e_metric",)),
        Binding(CONCLUSION, declared(done), ("C1",)),
    )
    assert table.step_for("rigor:r17:e_metric") == declared(report_metrics)
    assert table.step_for("C1") == declared(done)
    assert list(table) == list(table.bindings)
    assert len(table) == 2
    assert table.diagnostics == ()
    assert repr(table) == "BindingTable(2 bindings, 0 problems)"


def test_an_unbound_element_has_no_step() -> None:
    table = BindingTable(justification(METRIC), registry(done))
    assert table.step_for("rigor:r17:e_metric") is None
    assert table.diagnostics == ()


def test_several_ids_of_a_step_may_designate_its_element() -> None:
    table = BindingTable(justification(METRIC), registry(report_metrics_twice))
    assert table.bindings == (
        Binding(METRIC, declared(report_metrics_twice), ("rigor:r17:e_metric", "r17:e_metric")),
    )


def test_an_id_that_designates_no_element_is_jp015() -> None:
    @evidence("e_metrics")
    def typo() -> Outcome:
        return Pass()

    table = BindingTable(justification(METRIC), registry(typo))
    assert codes(table) == [(UNKNOWN_BINDING_TARGET, None)]
    assert table.bindings == ()


def test_a_step_with_one_unknown_id_still_binds_by_the_others() -> None:
    @evidence("e_metric", "e_metrics")
    def half_typo() -> Outcome:
        return Pass()

    table = BindingTable(justification(METRIC), registry(half_typo))
    assert codes(table) == [(UNKNOWN_BINDING_TARGET, None)]
    assert table.step_for(METRIC.id) == declared(half_typo)


def test_an_ambiguous_id_is_jp006() -> None:
    @evidence("e")
    def which() -> Outcome:
        return Pass()

    elements = (evidence_element("rigor:r17:e"), evidence_element("perf:r5:e"))
    table = BindingTable(justification(*elements), registry(which))
    assert codes(table) == [(AMBIGUOUS_BINDING, None)]
    assert table.bindings == ()


def test_an_element_bound_by_two_functions_is_jp007_and_left_unbound() -> None:
    @evidence("rigor:r17:e_metric")
    def again() -> Outcome:
        return Pass()

    table = BindingTable(justification(METRIC), registry(report_metrics, again, done))
    assert codes(table) == [(CONFLICTING_BINDING, METRIC.id)]
    assert table.step_for(METRIC.id) is None
    assert table.step_for("C1") == declared(done)


def test_a_function_bound_to_two_elements_is_jp007_and_left_unbound() -> None:
    @strategy("e_metric", "C1")
    def everything() -> Outcome:
        return Pass()

    table = BindingTable(justification(METRIC), registry(everything))
    assert codes(table) == [(CONFLICTING_BINDING, None)]
    assert table.bindings == ()


def test_every_problem_is_reported_together() -> None:
    @evidence("nowhere")
    def lost() -> Outcome:
        return Pass()

    @conclusion("rigor:C1")
    def also_done() -> Outcome:
        return Pass()

    table = BindingTable(justification(METRIC), registry(lost, done, also_done))
    assert codes(table) == [(UNKNOWN_BINDING_TARGET, None), (CONFLICTING_BINDING, "C1")]


# --- The e2e scenarios: real compiler output ---------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_every_scenario_binds_each_step_to_one_element(scenario: Scenario) -> None:
    with scenario.imported_libraries() as modules:
        registry = StepRegistry.from_modules(modules)
    table = BindingTable(loader.load(scenario.justification), registry)
    assert table.diagnostics == ()
    assert sorted(binding.step.name for binding in table) == sorted(s.name for s in registry)


def test_a_refined_hook_keeps_its_id_as_an_alias() -> None:
    # #116: `refine(draft, tested) { hook: "tests" }` merges draft's evidence `tests` and
    # tested's conclusion into one sub-conclusion. jPipe 2.5.0 keeps both ids as aliases,
    # so a step written against the standalone `draft` still binds after the refine.
    composed = loader.load(SCENARIOS_ROOT / "composed" / "justification.json")
    hook = composed.element("readiness:hook")
    assert hook.kind is Kind.SUB_CONCLUSION
    assert hook.aliases == ("readiness:draft:tests", "readiness:tested:tested")
    resolver = Resolver(composed)
    assert resolver.resolve("draft:tests") is hook
    assert resolver.resolve("tested:tested") is hook


def test_a_check_of_the_refined_hook_binds_to_it() -> None:
    @evidence("draft:tests")
    def the_test_suite_passes() -> Outcome:
        return Pass()

    composed = loader.load(SCENARIOS_ROOT / "composed" / "justification.json")
    table = BindingTable(composed, registry(the_test_suite_passes))
    assert table.diagnostics == ()
    assert table.step_for("readiness:hook") == declared(the_test_suite_passes)


def test_binding_both_ids_of_a_refined_hook_is_a_conflict() -> None:
    @evidence("draft:tests")
    def the_test_suite_passes() -> Outcome:
        return Pass()

    @conclusion("tested:tested")
    def the_code_is_tested() -> Outcome:
        return Pass()

    composed = loader.load(SCENARIOS_ROOT / "composed" / "justification.json")
    table = BindingTable(composed, registry(the_test_suite_passes, the_code_is_tested))
    assert codes(table) == [(CONFLICTING_BINDING, "readiness:hook")]
