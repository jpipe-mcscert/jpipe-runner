"""JP016 `IncompatibleKind`: a kind that composition does not explain (ADR-0036)."""

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
    element,
    model,
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
        pytest.param(
            "refine",
            step(CONCLUSION, "draft:documented"),
            [("JP016", ERROR, "readiness:draft:documented")],
            id="a conclusion step on an element written as a sub-conclusion",
        ),
        pytest.param(
            "refine",
            step(EVIDENCE, "readiness:hook"),
            [("JP016", ERROR, "readiness:hook")],
            id="the old kind, by the composed id",
        ),
        pytest.param(
            "chain",
            step(CONCLUSION, "mid:tested:suite"),
            [("JP016", ERROR, "top:hook")],
            id="the kind of an origin the step does not designate",
        ),
        pytest.param(
            "refine",
            step(EVIDENCE, "readiness:draft:tests"),
            [("JP016", ERROR, "readiness:hook")],
            id="the old kind, by an alias of the composed model",
        ),
        pytest.param(
            "assemble",
            step(CONCLUSION, "readiness:tested:tested"),
            [("JP016", ERROR, "readiness:tested:tested")],
            id="the old kind, by the assembled id",
        ),
        pytest.param("refine", step(EVIDENCE, "draft:tests"), [], id="refine: JP008"),
        pytest.param("assemble", step(CONCLUSION, "tested:tested"), [], id="assemble: JP008"),
        pytest.param("dominance", step(EVIDENCE, "checked:tests"), [], id="unification: JP008"),
        pytest.param("chain", step(EVIDENCE, "tested:suite"), [], id="chained: JP008"),
        pytest.param("refine", step(STRATEGY, "tested:testing"), [], id="the same kind"),
    ],
)
def test_a_kind_composition_does_not_explain_is_an_error(
    model: str, bound: Step, expected: list[Reported]
) -> None:
    assert reported(IncompatibleKind(), context(composed(model), bound)) == expected


def test_the_fix_names_the_id_the_element_had_with_the_step_s_kind() -> None:
    (error,) = IncompatibleKind().check(
        context(composed("refine"), step(EVIDENCE, "readiness:hook"))
    )

    assert error.fix == (
        "Declare it with @sub_conclusion, or bind it by the id the element had in 'draft': "
        "'draft:tests'."
    )


def test_a_model_without_origins_is_judged_by_kinds_alone() -> None:
    older = composed("refine", origins=False)

    (error,) = IncompatibleKind().check(context(older, step(EVIDENCE, "draft:tests")))

    assert error.element == "readiness:hook"
    assert error.fix == (
        "Declare it with @sub_conclusion. If the model was composed by a jPipe older than "
        "4.0.0, recompile it."
    )


def test_in_a_composed_model_the_fix_does_not_suggest_recompiling() -> None:
    (error,) = IncompatibleKind().check(context(composed("refine"), step(STRATEGY, "tested:suite")))

    assert error.fix == "Declare it with @evidence."


def test_a_mistake_composition_cannot_make_is_not_sent_to_the_compiler() -> None:
    older = composed("refine", origins=False)

    (error,) = IncompatibleKind().check(context(older, step(STRATEGY, "tested:suite")))

    assert error.fix == "Declare it with @evidence."


def test_a_model_never_composed_excuses_nothing() -> None:
    written = model(element("c", CONCLUSION), element("s", SUB_CONCLUSION), relations=[("s", "c")])

    assert reported(IncompatibleKind(), context(written, step(EVIDENCE, "s"))) == [
        ("JP016", ERROR, "s")
    ]
