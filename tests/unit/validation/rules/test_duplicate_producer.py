"""JP010 `DuplicateProducer`: a variable has one producer."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import DuplicateProducer
from jpipe_runner.steps import Step
from tests.unit.validation.builders import (
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
    element("m:e1", EVIDENCE),
    element("m:e2", EVIDENCE),
    element("m:s", STRATEGY),
    relations=[("m:e1", "m:s"), ("m:e2", "m:s")],
)


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param(
            [
                step(EVIDENCE, "m:e1", produces=["x"], name="f"),
                step(EVIDENCE, "m:e2", produces=["x"], name="g"),
            ],
            [("JP010", Severity.ERROR, None)],
            id="two evidence",
        ),
        pytest.param(
            [
                step(EVIDENCE, "m:e1", produces=["x"], name="f"),
                step(EVIDENCE, "m:e2", produces=["y"], name="g"),
                step(STRATEGY, "m:s", produces=["x", "y"], name="h"),
            ],
            [("JP010", Severity.ERROR, None), ("JP010", Severity.ERROR, None)],
            id="one diagnostic per variable",
        ),
        pytest.param(
            [
                step(EVIDENCE, "m:e1", produces=["x"], name="f"),
                step(EVIDENCE, "m:e2", produces=["y"], name="g"),
            ],
            [],
            id="distinct names",
        ),
    ],
)
def test_a_variable_produced_twice_is_reported(steps: list[Step], expected: list[Reported]) -> None:
    assert reported(DuplicateProducer(), context(MODEL, *steps)) == expected
