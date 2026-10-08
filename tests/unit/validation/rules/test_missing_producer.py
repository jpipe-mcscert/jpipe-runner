"""JP009 `MissingProducer`: every consumed variable has a producer."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import MissingProducer
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
ERROR = Severity.ERROR


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param(
            [step(EVIDENCE, "m:e"), step(STRATEGY, "m:s", consumes=["x"])],
            [("JP009", ERROR, "m:s")],
            id="nothing produces it",
        ),
        pytest.param(
            [
                step(EVIDENCE, "m:x", produces=["x"]),
                step(STRATEGY, "m:s", consumes=["x"]),
            ],
            [("JP009", ERROR, "m:s")],
            id="only a step that binds nothing produces it",
        ),
        pytest.param(
            [
                step(EVIDENCE, "m:e", produces=["x"]),
                step(STRATEGY, "m:s", consumes=["x", "y"]),
                step(CONCLUSION, "m:c", consumes=["y"]),
            ],
            [("JP009", ERROR, "m:s"), ("JP009", ERROR, "m:c")],
            id="one diagnostic per consumer",
        ),
        pytest.param(
            [step(EVIDENCE, "m:e", produces=["x"]), step(STRATEGY, "m:s", consumes=["x"])],
            [],
            id="produced",
        ),
    ],
)
def test_a_variable_nothing_produces_is_reported(
    steps: list[Step], expected: list[Reported]
) -> None:
    assert reported(MissingProducer(), context(MODEL, *steps)) == expected
