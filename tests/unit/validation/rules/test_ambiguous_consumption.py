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
