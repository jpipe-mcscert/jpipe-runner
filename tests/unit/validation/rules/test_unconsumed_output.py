"""JP011 `UnconsumedOutput`: a produced variable is consumed."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import UnconsumedOutput
from jpipe_runner.steps import Step
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    STRATEGY,
    Reported,
    context,
    element,
    model,
    reported,
    step,
)

MODEL = model(
    element("m:e", EVIDENCE),
    element("m:s", STRATEGY),
    element("m:c", CONCLUSION),
    relations=[("m:e", "m:s"), ("m:s", "m:c")],
)
WARNING = Severity.WARNING


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param(
            [
                step(EVIDENCE, "m:e", produces=["x"]),
                step(STRATEGY, "m:s", consumes=["x"], produces=["y"]),
            ],
            [("JP011", WARNING, "m:s")],
            id="a strategy's output",
        ),
        pytest.param(
            [step(EVIDENCE, "m:e", produces=["x", "z"]), step(STRATEGY, "m:s", consumes=["x"])],
            [("JP011", WARNING, "m:e")],
            id="one of an evidence's outputs",
        ),
        pytest.param(
            [step(EVIDENCE, "m:e", produces=["z"]), step(STRATEGY, "m:s")],
            [],
            id="all of an evidence's outputs: JP012",
        ),
        pytest.param(
            [
                step(EVIDENCE, "m:e", produces=["x"]),
                step(STRATEGY, "m:s", consumes=["x"], produces=["y"]),
                step(CONCLUSION, "m:c", consumes=["y"]),
            ],
            [],
            id="consumed",
        ),
    ],
)
def test_a_variable_nothing_consumes_is_a_warning(
    steps: list[Step], expected: list[Reported]
) -> None:
    assert reported(UnconsumedOutput(), context(MODEL, *steps)) == expected
