"""JP013 `StrategyIgnoresUpstreamOutput`: a strategy consumes what its supporters produce."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import StrategyIgnoresUpstreamOutput
from jpipe_runner.steps import Step
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

MODEL = model(
    element("m:e1", EVIDENCE),
    element("m:e2", EVIDENCE),
    element("m:sc", SUB_CONCLUSION),
    element("m:s", STRATEGY),
    element("m:c", CONCLUSION),
    relations=[("m:e1", "m:s"), ("m:e2", "m:s"), ("m:sc", "m:s"), ("m:s", "m:c")],
)
WARNING = Severity.WARNING
E1 = step(EVIDENCE, "m:e1", produces=["a"], name="e1")
E2 = step(EVIDENCE, "m:e2", produces=["b"], name="e2")


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param(
            [
                E1,
                E2,
                step(STRATEGY, "m:s", consumes=["a"]),
                step(CONCLUSION, "m:c", consumes=["b"]),
            ],
            [("JP013", WARNING, "m:s")],
            id="read only further up",
        ),
        pytest.param(
            [E1, E2, step(STRATEGY, "m:s", consumes=["a", "b"])],
            [],
            id="consumes both",
        ),
        pytest.param(
            [E1, E2, step(STRATEGY, "m:s", consumes=["a"])],
            [],
            id="read by nobody: JP011 or JP012",
        ),
        pytest.param(
            [E1, E2, step(CONCLUSION, "m:c", consumes=["a", "b"])],
            [],
            id="no strategy step: JP005",
        ),
        pytest.param(
            [
                E1,
                E2,
                step(SUB_CONCLUSION, "m:sc", produces=["d"], name="sc"),
                step(STRATEGY, "m:s", consumes=["a", "b"]),
                step(CONCLUSION, "m:c", consumes=["d"]),
            ],
            [("JP013", WARNING, "m:s")],
            id="a bound sub-conclusion's output",
        ),
    ],
)
def test_a_strategy_ignoring_its_supporters_values_is_a_warning(
    steps: list[Step], expected: list[Reported]
) -> None:
    assert reported(StrategyIgnoresUpstreamOutput(), context(MODEL, *steps)) == expected
