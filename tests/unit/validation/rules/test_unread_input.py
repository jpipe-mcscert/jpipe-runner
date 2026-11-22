"""JP027 `UnreadInput`: a step reads what it consumes and what it observes (ADR-0037)."""

from pathlib import Path
from typing import Any

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy
from jpipe_runner.diagnostics import Severity
from jpipe_runner.rules import UnreadInput
from jpipe_runner.steps import Step, step_of
from tests.unit.validation.builders import (
    EVIDENCE,
    STRATEGY,
    context,
    element,
    model,
    reported,
)

MODEL = model(element("s", STRATEGY), element("e", EVIDENCE), relations=[("e", "s")])
WARNING = Severity.WARNING


def _step(function: Any) -> Step:
    found = step_of(function)
    assert found is not None
    return found


@evidence("e", observes={"log": "CHANGELOG.md"}, produces=["coverage"])
def unread_log(log: Path) -> Outcome:
    return Pass(coverage=0.9)


@evidence("e", observes={"log": "CHANGELOG.md"}, produces=["coverage"])
def read_log(log: Path) -> Outcome:
    return Pass(coverage=len(log.name))


@strategy("s", consumes=["coverage", "threshold"])
def ignores(coverage: float, threshold: float) -> Outcome:
    return Pass()


@strategy("s", consumes=["coverage"])
def judges(coverage: float) -> Outcome:
    return Pass() if coverage > 0.8 else Fail("low")


@strategy("s", consumes=["coverage", "threshold"])
def swallows(**kwargs: Any) -> Outcome:
    return Pass()


def test_an_unread_input_is_a_warning_on_its_element() -> None:
    ctx = context(MODEL, _step(unread_log), _step(ignores))

    assert reported(UnreadInput(), ctx) == [("JP027", WARNING, "s"), ("JP027", WARNING, "e")]


def test_a_step_that_reads_everything_is_not_reported() -> None:
    assert reported(UnreadInput(), context(MODEL, _step(read_log), _step(judges))) == []


def test_the_warning_names_what_is_unread_and_how_it_is_declared() -> None:
    (strategy_warning, evidence_warning) = UnreadInput().check(
        context(MODEL, _step(unread_log), _step(ignores))
    )

    assert strategy_warning.message == (
        f"{__name__}.ignores never reads 'coverage' and 'threshold', which it consumes: the "
        "argument claims a dependency the step does not have"
    )
    assert strategy_warning.fix == (
        "Read them in the step, or remove them from consumes and from the function's parameters."
    )
    assert evidence_warning.fix == (
        "Read it in the step, or remove it from observes and from the function's parameters."
    )


def test_inputs_taken_only_through_kwargs_are_reported_as_unchecked() -> None:
    (warning,) = UnreadInput().check(context(MODEL, _step(read_log), _step(swallows)))

    assert warning.message == (
        f"{__name__}.swallows takes 'coverage' and 'threshold', which it consumes, only "
        "through **kwargs, so whether it reads them cannot be checked"
    )
    assert warning.fix == "Name them as parameters of the function."


def test_a_step_that_binds_nothing_is_not_checked() -> None:
    elsewhere = model(element("other", STRATEGY))

    assert reported(UnreadInput(), context(elsewhere, _step(ignores))) == []
