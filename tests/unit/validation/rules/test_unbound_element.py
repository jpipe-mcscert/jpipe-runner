"""JP005 `UnboundElement`: every evidence and strategy has a step."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import UnboundElement
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
    element("m:e", EVIDENCE),
    element("m:s", STRATEGY),
    element("m:sc", SUB_CONCLUSION),
    element("m:c", CONCLUSION),
    relations=[("m:e", "m:s"), ("m:s", "m:sc"), ("m:sc", "m:c")],
)
ERROR = Severity.ERROR


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param([], [("JP005", ERROR, "m:e"), ("JP005", ERROR, "m:s")], id="no step"),
        pytest.param([step(EVIDENCE, "m:e")], [("JP005", ERROR, "m:s")], id="no strategy step"),
        pytest.param(
            [step(EVIDENCE, "m:e"), step(STRATEGY, "m:s")],
            [],
            id="sub-conclusion and conclusion are optional",
        ),
        pytest.param(
            [step(EVIDENCE, "m:e", name="f"), step(EVIDENCE, "e", name="g"), step(STRATEGY, "s")],
            [],
            id="claimed twice: JP007",
        ),
    ],
)
def test_an_evidence_or_strategy_without_a_step_is_reported(
    steps: list[Step], expected: list[Reported]
) -> None:
    assert reported(UnboundElement(), context(MODEL, *steps)) == expected
