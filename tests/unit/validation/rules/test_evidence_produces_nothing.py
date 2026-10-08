"""JP012 `EvidenceProducesNothing`: an evidence produces a value another step consumes."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import EvidenceProducesNothing
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
    element("m:sc", SUB_CONCLUSION),
    element("m:s", STRATEGY),
    element("m:c", CONCLUSION),
    relations=[("m:e", "m:s"), ("m:sc", "m:s"), ("m:s", "m:c")],
)
ERROR = Severity.ERROR


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param([step(EVIDENCE, "m:e")], [("JP012", ERROR, "m:e")], id="produces nothing"),
        pytest.param(
            [step(EVIDENCE, "m:e", produces=["x"]), step(STRATEGY, "m:s")],
            [("JP012", ERROR, "m:e")],
            id="produces what no step consumes",
        ),
        pytest.param(
            [step(EVIDENCE, "m:sc"), step(STRATEGY, "m:s")],
            [("JP012", ERROR, "m:sc")],
            id="the step's kind decides, not the element's",
        ),
        pytest.param(
            [step(EVIDENCE, "m:e", produces=["x", "y"]), step(STRATEGY, "m:s", consumes=["x"])],
            [],
            id="one value consumed",
        ),
        pytest.param(
            [step(EVIDENCE, "m:e", produces=["x"]), step(CONCLUSION, "m:c", consumes=["x"])],
            [],
            id="consumed further up",
        ),
        pytest.param([step(SUB_CONCLUSION, "m:sc")], [], id="not an evidence"),
    ],
)
def test_an_evidence_whose_values_nothing_consumes_is_an_error(
    steps: list[Step], expected: list[Reported]
) -> None:
    assert reported(EvidenceProducesNothing(), context(MODEL, *steps)) == expected
