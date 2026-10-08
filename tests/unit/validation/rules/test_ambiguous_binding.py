"""JP006 `AmbiguousBinding`: reports what the binding table found under its code (ADR-0007).

Resolution itself is tested in tests/unit/test_binding.py.
"""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import AmbiguousBinding
from jpipe_runner.steps import Step
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    Reported,
    context,
    element,
    model,
    reported,
    step,
)

MODEL = model(
    element("m:a:e", EVIDENCE),
    element("m:b:e", EVIDENCE),
    element("m:c", CONCLUSION),
    relations=[("m:a:e", "m:c"), ("m:b:e", "m:c")],
)


@pytest.mark.parametrize(
    ("steps", "expected"),
    [
        pytest.param([step(EVIDENCE, "e")], [("JP006", Severity.ERROR, None)], id="a shared tail"),
        pytest.param([step(EVIDENCE, "a:e")], [], id="a unique tail"),
        pytest.param([step(EVIDENCE, "m:x")], [], id="no element: JP015"),
    ],
)
def test_an_id_designating_several_elements_is_reported(
    steps: list[Step], expected: list[Reported]
) -> None:
    assert reported(AmbiguousBinding(), context(MODEL, *steps)) == expected
