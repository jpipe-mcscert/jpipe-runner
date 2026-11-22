"""JP008 `RefinedElement`: a kind that composition changed (ADR-0036).

Each transition jPipe 4.0.0 produces is checked on its compiled output, with steps written
against the source models, as an author would before anyone composed them. The compiler
names each element's origins, and a step is excused only through one of them.
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
            step(EVIDENCE, "readiness:draft:tests"),
            [("JP008", WARNING, "readiness:hook")],
            id="an origin's id qualified by the model's name",
        ),
        pytest.param(
            "chain",
            step(EVIDENCE, "tested:suite"),
            [("JP008", WARNING, "top:hook")],
            id="chained: an origin two levels down",
        ),
        pytest.param(
            "chain",
            step(CONCLUSION, "covered"),
            [("JP008", WARNING, "top:hook")],
            id="chained: a tail of an origin's id",
        ),
        pytest.param("refine", step(CONCLUSION, "draft:documented"), [], id="written so: JP016"),
        pytest.param("refine", step(EVIDENCE, "readiness:hook"), [], id="the composed id: JP016"),
        pytest.param("refine", step(SUB_CONCLUSION, "draft:tests"), [], id="declared as it now is"),
        pytest.param("refine", step(EVIDENCE, "tested:suite"), [], id="an unchanged evidence"),
        pytest.param("refine", step(STRATEGY, "tested:suite"), [], id="a mistake: JP016"),
    ],
)
def test_a_kind_changed_by_composition_is_a_warning(
    model: str, bound: Step, expected: list[Reported]
) -> None:
    assert reported(RefinedElement(), context(composed(model), bound)) == expected


def test_without_origins_nothing_excuses_a_kind() -> None:
    older = composed("refine", origins=False)

    assert reported(RefinedElement(), context(older, step(EVIDENCE, "draft:tests"))) == []


def test_the_warning_names_the_origin_the_step_was_written_for() -> None:
    (warning,) = RefinedElement().check(context(composed("refine"), step(EVIDENCE, "draft:tests")))

    assert warning.message == (
        "tests.unit.validation.builders.f is declared as evidence, for 'draft:tests' in 'draft', which composition made the "
        "sub-conclusion 'readiness:hook': it runs as a cross-check of the argument below it"
    )
    assert warning.fix == (
        "Nothing to do for a cross-check. If the library serves only the composed model, "
        "declare the step with @sub_conclusion."
    )
