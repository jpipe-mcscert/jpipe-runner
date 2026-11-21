"""JP025 `AmbiguousConsumption`: a consumed variable resolves to one supporter (ADR-0031)."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import AmbiguousConsumption
from jpipe_runner.steps import Produced, Step
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    STRATEGY,
    SUB_CONCLUSION,
    Reported,
    context,
    element,
    model,
    reported,
    step,
)

# Two sub-arguments, as `assemble` builds them: e1 -> s1 -> c1 and e2 -> s2 -> c2, both
# supporting s -> c.
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
ERROR = Severity.ERROR

# Each source's library: its evidence produces `x`, which its strategy consumes.
SOURCES = [
    step(EVIDENCE, "m:a:e", produces=["x"], name="a_e"),
    step(STRATEGY, "m:a:s", consumes=["x"], name="a_s"),
    step(EVIDENCE, "m:b:e", produces=["x"], name="b_e"),
    step(STRATEGY, "m:b:s", consumes=["x"], name="b_s"),
]


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param(SOURCES, [], id="each consumer sees its own producer"),
        pytest.param(
            [*SOURCES, step(STRATEGY, "m:s", consumes=["x"], name="s")],
            [("JP025", ERROR, "m:s")],
            id="a consumer above both",
        ),
        pytest.param(
            [*SOURCES, step(CONCLUSION, "m:c", consumes=["x"], name="c")],
            [("JP025", ERROR, "m:c")],
            id="an indirect consumer above both",
        ),
        pytest.param(
            [
                *SOURCES,
                step(STRATEGY, "m:s", consumes={"x": Produced("x", by="m:a:e")}, name="s"),
            ],
            [],
            id="by the producer",
        ),
        pytest.param(
            [
                *SOURCES,
                step(
                    STRATEGY,
                    "m:s",
                    consumes={"a": Produced("x", by="a:c"), "b": Produced("x", by="b:c")},
                    name="s",
                ),
            ],
            [],
            id="both, each by its sub-argument",
        ),
        pytest.param(
            [*SOURCES, step(STRATEGY, "m:s", consumes={"x": Produced("x", by="m:s")}, name="s")],
            [("JP025", ERROR, "m:s")],
            id="by an element above both",
        ),
    ],
)
def test_a_variable_two_supporters_produce_is_ambiguous(
    steps: list[Step], expected: list[Reported]
) -> None:
    assert reported(AmbiguousConsumption(), context(MODEL, *steps)) == expected


# A chain, e -> s -> c, in which e and s both produce `x`.
CHAIN = model(
    element("m:e", EVIDENCE),
    element("m:s", STRATEGY),
    element("m:c", CONCLUSION),
    relations=[("m:e", "m:s"), ("m:s", "m:c")],
)
LINKS = [
    step(EVIDENCE, "m:e", produces=["x"], name="e"),
    step(STRATEGY, "m:s", consumes=["x"], produces=["x"], name="s"),
]


@pytest.mark.parametrize(
    ("consumes", "expected"),
    [
        pytest.param(["x"], [("JP025", ERROR, "m:c")], id="both producers support it"),
        pytest.param({"x": Produced("x", by="m:s")}, [], id="by the producer above"),
        pytest.param({"x": Produced("x", by="m:e")}, [], id="by the producer below"),
    ],
)
def test_by_designating_a_producer_selects_it_even_above_another(
    consumes: list[str] | dict[str, Produced], expected: list[Reported]
) -> None:
    ctx = context(CHAIN, *LINKS, step(CONCLUSION, "m:c", consumes=consumes, name="c"))
    assert reported(AmbiguousConsumption(), ctx) == expected


def test_the_fix_it_suggests_resolves_the_ambiguity() -> None:
    ctx = context(CHAIN, *LINKS, step(CONCLUSION, "m:c", consumes=["x"], name="c"))
    (diagnostic,) = AmbiguousConsumption().check(ctx)
    assert diagnostic.fix == (
        'Name the one it means, keeping the other entries of consumes: "x": '
        'Produced("x", by="m:e").'
    )
    fixed = step(CONCLUSION, "m:c", consumes={"x": Produced("x", by="m:e")}, name="c")
    assert reported(AmbiguousConsumption(), context(CHAIN, *LINKS, fixed)) == []


def test_two_parameters_receiving_one_ambiguous_variable_are_one_problem() -> None:
    a_c = step(SUB_CONCLUSION, "m:a:c", produces=["y"], name="a_c")
    gates = step(STRATEGY, "m:s", consumes={"a": "x", "b": "x", "c": "y"}, name="s")
    (diagnostic,) = AmbiguousConsumption().check(context(MODEL, *SOURCES, a_c, gates))
    assert (diagnostic.code, diagnostic.element) == ("JP025", "m:s")
    # Each parameter that receives the variable gets its entry; "c" is left as it is.
    assert diagnostic.fix == (
        "Name the one each parameter means, keeping the other entries of consumes: "
        '"a": Produced("x", by="m:a:e"), "b": Produced("x", by="m:a:e").'
    )
