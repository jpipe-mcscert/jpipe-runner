"""JP018 `EvidenceObservesNothing`: an evidence observes an artifact (ADR-0018)."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import EvidenceObservesNothing
from jpipe_runner.steps import Step
from tests.unit.validation.builders import (
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
    relations=[("m:e", "m:s"), ("m:sc", "m:s")],
)
ERROR = Severity.ERROR
LOG = {"log": "build/tests.log"}


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param([step(EVIDENCE, "m:e")], [("JP018", ERROR, "m:e")], id="observes nothing"),
        pytest.param(
            [step(EVIDENCE, "m:sc")],
            [("JP018", ERROR, "m:sc")],
            id="the step's kind decides, not the element's",
        ),
        pytest.param([step(EVIDENCE, "m:e", observes=LOG)], [], id="observes a file"),
        pytest.param([step(SUB_CONCLUSION, "m:sc")], [], id="not an evidence"),
        pytest.param([step(EVIDENCE, "m:x")], [], id="binds nothing: JP015"),
    ],
)
def test_an_evidence_observing_nothing_is_an_error(
    steps: list[Step], expected: list[Reported]
) -> None:
    assert reported(EvidenceObservesNothing(), context(MODEL, *steps)) == expected
