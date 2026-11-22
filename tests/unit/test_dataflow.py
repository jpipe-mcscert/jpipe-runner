"""The dataflow table: each consumed variable resolved among its consumer's supporters
(ADR-0031)."""

from jpipe_runner.binding import Binding
from jpipe_runner.dataflow import DataflowTable, Received
from jpipe_runner.diagnostics import Severity
from jpipe_runner.steps import Produced, Step
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    STRATEGY,
    SUB_CONCLUSION,
    context,
    element,
    model,
    step,
)

# Two sub-arguments, a:e -> a:s -> a:c and b:e -> b:s -> b:c, both supporting s -> c.
MODEL = model(
    element("m:a:e", EVIDENCE),
    element("m:a:s", STRATEGY),
    element("m:a:c", SUB_CONCLUSION),
    element("m:b:e", EVIDENCE),
    element("m:b:s", STRATEGY),
    element("m:b:c", SUB_CONCLUSION),
    element("m:s", STRATEGY),
    element("m:c", CONCLUSION),
    relations=[
        ("m:a:e", "m:a:s"),
        ("m:a:s", "m:a:c"),
        ("m:b:e", "m:b:s"),
        ("m:b:s", "m:b:c"),
        ("m:a:c", "m:s"),
        ("m:b:c", "m:s"),
        ("m:s", "m:c"),
    ],
)

A_E = step(EVIDENCE, "m:a:e", produces=["x"], name="a_e")
A_S = step(STRATEGY, "m:a:s", consumes=["x"], name="a_s")
B_E = step(EVIDENCE, "m:b:e", produces=["x"], name="b_e")
B_S = step(STRATEGY, "m:b:s", consumes=["x"], name="b_s")


def table(*steps: Step) -> DataflowTable:
    return context(MODEL, *steps).dataflow


def ids(*found: Binding | None) -> list[str]:
    """The element ids of ``found``, ``-`` for none."""
    return ["-" if binding is None else binding.element.id for binding in found]


def test_a_variable_resolves_to_the_producer_among_the_consumers_supporters() -> None:
    dataflow = table(A_E, A_S, B_E, B_S)
    a, b = dataflow.of("m:a:s") + dataflow.of("m:b:s")
    assert (ids(*a.producers), ids(*a.candidates)) == (["m:a:e", "m:b:e"], ["m:a:e"])
    assert ids(a.producer, b.producer) == ["m:a:e", "m:b:e"]
    assert dataflow.diagnostics == ()
    assert (len(dataflow), repr(dataflow)) == (2, "DataflowTable(2 inputs)")


def test_a_consumer_above_both_has_two_candidates_and_no_producer() -> None:
    (above,) = table(A_E, B_E, step(STRATEGY, "m:s", consumes=["x"])).of("m:s")
    assert ids(*above.candidates) == ["m:a:e", "m:b:e"]
    assert above.producer is None


def test_by_narrows_the_candidates_to_an_element_and_its_supporters() -> None:
    gates = step(
        STRATEGY,
        "m:s",
        consumes={"a": Produced("x", by="a:c"), "b": Produced("x", by="m:b:e")},
    )
    dataflow = table(A_E, B_E, gates)
    a, b = dataflow.of("m:s")
    assert (a.within and a.within.id, ids(*a.reachable)) == ("m:a:c", ["m:a:e"])
    assert (b.within and b.within.id, ids(*b.reachable)) == ("m:b:e", ["m:b:e"])
    assert dataflow.received("m:s") == (Received("a", "x", "m:a:e"), Received("b", "x", "m:b:e"))


def test_a_by_that_designates_no_element_or_several_is_reported() -> None:
    gates = step(
        STRATEGY,
        "m:s",
        consumes={"a": Produced("x", by="m:nowhere"), "b": Produced("x", by="e")},
    )
    dataflow = table(A_E, B_E, gates)
    assert [(d.code, d.severity, d.element) for d in dataflow.diagnostics] == [
        ("JP015", Severity.ERROR, "m:s"),
        ("JP006", Severity.ERROR, "m:s"),
    ]
    assert all(not c.designated and not c.candidates for c in dataflow.of("m:s"))
    assert dataflow.received("m:s") == (Received("a", "x", None), Received("b", "x", None))


def test_a_producer_is_used_by_the_inputs_that_draw_on_it() -> None:
    dataflow = table(A_E, A_S, B_E)
    assert [c.consumer.element.id for c in dataflow.users("m:a:e", "x")] == ["m:a:s"]
    assert dataflow.users("m:b:e", "x") == ()


def test_an_input_no_supporter_provides_draws_on_the_producers_it_names() -> None:
    # The producer is on another branch (JP014): it still counts as consumed, so that
    # JP011 and JP012 do not report it too.
    dataflow = table(B_E, A_S)
    (consumed,) = dataflow.of("m:a:s")
    assert (consumed.candidates, ids(*consumed.sources)) == ((), ["m:b:e"])
    assert [c.consumer.element.id for c in dataflow.users("m:b:e", "x")] == ["m:a:s"]
