"""JP016 `IncompatibleKind`: a kind that composition cannot explain (ADR-0013)."""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import IncompatibleKind
from jpipe_runner.steps import Step
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    STRATEGY,
    SUB_CONCLUSION,
    Reported,
    composed,
    context,
    reported,
    step,
)

ERROR = Severity.ERROR


@pytest.mark.parametrize(
    ("model", "bound", "expected"),
    [
        pytest.param(
            "refine",
            step(STRATEGY, "tested:suite"),
            [("JP016", ERROR, "readiness:tested:suite")],
            id="a strategy step on an evidence",
        ),
        pytest.param(
            "refine",
            step(EVIDENCE, "tested:testing"),
            [("JP016", ERROR, "readiness:tested:testing")],
            id="an evidence step on a strategy",
        ),
        pytest.param(
            "refine",
            step(SUB_CONCLUSION, "draft:ready"),
            [("JP016", ERROR, "readiness:draft:ready")],
            id="a sub-conclusion step on the conclusion",
        ),
        pytest.param(
            "assemble",
            step(STRATEGY, "tested:tested"),
            [("JP016", ERROR, "readiness:tested:tested")],
            id="a strategy step on a sub-conclusion",
        ),
        pytest.param("refine", step(EVIDENCE, "draft:tests"), [], id="refine: JP008"),
        pytest.param("assemble", step(CONCLUSION, "tested:tested"), [], id="assemble: JP008"),
        pytest.param("dominance", step(EVIDENCE, "checked:tests"), [], id="unification: JP008"),
        pytest.param("refine", step(STRATEGY, "tested:testing"), [], id="the same kind"),
    ],
)
def test_a_kind_composition_cannot_produce_is_an_error(
    model: str, bound: Step, expected: list[Reported]
) -> None:
    assert reported(IncompatibleKind(), context(composed(model), bound)) == expected
