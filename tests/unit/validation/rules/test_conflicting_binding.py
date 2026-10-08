"""JP007 `ConflictingBinding`: reports what the binding table found under its code (ADR-0007).

Resolution itself is tested in tests/unit/test_binding.py.
"""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import ConflictingBinding
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
        pytest.param(
            [step(EVIDENCE, "a:e", name="f"), step(EVIDENCE, "m:a:e", name="g")],
            [("JP007", Severity.ERROR, "m:a:e")],
            id="one element, two steps",
        ),
        pytest.param(
            [step(EVIDENCE, "a:e", "b:e")],
            [("JP007", Severity.ERROR, None)],
            id="one step, two elements",
        ),
        pytest.param([step(EVIDENCE, "a:e", "m:a:e")], [], id="two ids of one element"),
        pytest.param(
            [step(EVIDENCE, "a:e", name="f"), step(EVIDENCE, "b:e", name="g")],
            [],
            id="two steps, two elements",
        ),
    ],
)
def test_binding_is_one_to_one(steps: list[Step], expected: list[Reported]) -> None:
    assert reported(ConflictingBinding(), context(MODEL, *steps)) == expected
