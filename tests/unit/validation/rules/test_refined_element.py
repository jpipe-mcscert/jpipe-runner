"""JP008 `RefinedElement`: a kind that composition changed (ADR-0013).

Each transition jPipe 2.5.0 produces is checked on its compiled output, with steps written
against the source models, as an author would before anyone composed them.
"""

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import RefinedElement
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

WARNING = Severity.WARNING


@pytest.mark.parametrize(
    ("model", "bound", "expected"),
    [
        pytest.param(
            "refine",
            step(EVIDENCE, "draft:tests"),
            [("JP008", WARNING, "readiness:hook")],
            id="refine: the hook evidence",
        ),
        pytest.param(
            "refine",
            step(CONCLUSION, "tested:tested"),
            [("JP008", WARNING, "readiness:hook")],
            id="refine: the refinement's conclusion",
        ),
        pytest.param(
            "assemble",
            step(CONCLUSION, "tested:tested"),
            [("JP008", WARNING, "readiness:tested:tested")],
            id="assemble: a source's conclusion",
        ),
        pytest.param(
            "dominance",
            step(EVIDENCE, "checked:tests"),
            [("JP008", WARNING, "release:unified_0")],
            id="unification: an evidence merged into a sub-conclusion",
        ),
        pytest.param(
            "refine",
            step(CONCLUSION, "draft:documented"),
            [("JP008", WARNING, "readiness:draft:documented")],
            id="kinds alone decide, not provenance",
        ),
        pytest.param("refine", step(SUB_CONCLUSION, "draft:tests"), [], id="declared as it now is"),
        pytest.param("refine", step(EVIDENCE, "tested:suite"), [], id="an unchanged evidence"),
        pytest.param("refine", step(STRATEGY, "tested:suite"), [], id="a mistake: JP016"),
    ],
)
def test_a_kind_changed_by_composition_is_a_warning(
    model: str, bound: Step, expected: list[Reported]
) -> None:
    assert reported(RefinedElement(), context(composed(model), bound)) == expected
