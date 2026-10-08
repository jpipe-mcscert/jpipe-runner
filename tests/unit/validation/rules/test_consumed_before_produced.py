"""JP014 `ConsumedBeforeProduced`: a variable's producer supports its consumer."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import ConsumedBeforeProduced
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

# Two branches: e1 -> s1 -> c and e2 -> s2 -> c.
MODEL = model(
    element("m:e1", EVIDENCE),
    element("m:e2", EVIDENCE),
    element("m:s1", STRATEGY),
    element("m:s2", STRATEGY),
    element("m:c", CONCLUSION),
    relations=[("m:e1", "m:s1"), ("m:e2", "m:s2"), ("m:s1", "m:c"), ("m:s2", "m:c")],
)
ERROR = Severity.ERROR


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param(
            [step(EVIDENCE, "m:e2", produces=["x"]), step(STRATEGY, "m:s1", consumes=["x"])],
            [("JP014", ERROR, "m:s1")],
            id="produced on another branch",
        ),
        pytest.param(
            [step(STRATEGY, "m:s1", consumes=["y"], produces=["y"])],
            [("JP014", ERROR, "m:s1")],
            id="consumes what it produces",
        ),
        pytest.param(
            [step(STRATEGY, "m:s1", produces=["y"]), step(EVIDENCE, "m:e1", produces=["y"])],
            [],
            id="nothing consumes it",
        ),
        pytest.param(
            [step(EVIDENCE, "m:e1", produces=["x"]), step(STRATEGY, "m:s1", consumes=["x"])],
            [],
            id="a direct supporter",
        ),
        pytest.param(
            [step(EVIDENCE, "m:e1", produces=["x"]), step(CONCLUSION, "m:c", consumes=["x"])],
            [],
            id="an indirect supporter",
        ),
        pytest.param([step(STRATEGY, "m:s1", consumes=["x"])], [], id="no producer: JP009"),
    ],
)
def test_a_producer_that_does_not_support_its_consumer_is_reported(
    steps: list[Step], expected: list[Reported]
) -> None:
    assert reported(ConsumedBeforeProduced(), context(MODEL, *steps)) == expected
