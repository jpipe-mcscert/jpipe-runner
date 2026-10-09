"""The report model: one report for every way a run ends (#121, ADR-0011)."""

from collections.abc import Callable
from pathlib import Path

import pytest

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy
from jpipe_runner.diagnostics import Diagnostic, Severity, shown_path, user_traceback
from jpipe_runner.engine import STEP_RAISED, Status, Verdict, run
from jpipe_runner.libraries import LibraryLoadError
from jpipe_runner.model import InvalidJustificationError
from jpipe_runner.report import ElementReport, Frame, RunReport, Summary, Trace
from jpipe_runner.steps import StepRegistry, step_of
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    STRATEGY,
    element,
    model,
)

HERE = Path(__file__).parent
MODULE = __name__

# e1 and e2 support s, which supports c; c is listed first, so model order is not run order.
RELEASE = model(
    element("c", CONCLUSION),
    element("s", STRATEGY),
    element("e1", EVIDENCE, "old:e1"),
    element("e2", EVIDENCE),
    relations=[("s", "c"), ("e1", "s"), ("e2", "s")],
)


def _registry(*functions: Callable[..., Outcome]) -> StepRegistry:
    return StepRegistry(step for step in map(step_of, functions) if step is not None)


@evidence("old:e1", observes={"log": "e1.txt"}, produces=["a"])
def first(log: Path) -> Outcome:
    return Pass(a=log.read_text(encoding="utf-8"))


@evidence("e2", observes={"logs": "*.txt"}, produces=["b"])
def second(logs: list[Path]) -> Outcome:
    return Fail(f"{len(logs)} logs")


@strategy("s", consumes=["a", "b"])
def gates(a: str, b: int) -> Outcome:
    return Pass()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "e1.txt").write_text("one", encoding="utf-8")
    return tmp_path


def _report(root: Path, *functions: Callable[..., Outcome], **options: bool) -> RunReport:
    result = run(RELEASE, _registry(*functions), root=root, **options)
    return RunReport.of(result, root)


def test_a_run_lists_every_element_in_the_order_run(root: Path) -> None:
    report = _report(root, first, second, gates)

    assert (report.justification, report.verdict) == ("m", Verdict.FAIL)
    assert [e.id for e in report.elements] == ["e1", "e2", "s", "c"]
    assert [e.status for e in report.elements] == [
        Status.PASS,
        Status.FAIL,
        Status.SKIP,
        Status.SKIP,
    ]
    assert report.diagnostics == ()
    assert report.ran


def test_an_element_carries_its_binding_declarations_and_what_it_observed(root: Path) -> None:
    e1 = _report(root, first, second, gates).elements[0]

    assert (e1.id, e1.label, e1.kind, e1.aliases, e1.supports) == (
        "e1",
        "e1",
        EVIDENCE,
        ("old:e1",),
        ("s",),
    )
    assert (e1.step, e1.designators) == (f"{MODULE}.first", ("old:e1",))
    assert (e1.observes, e1.consumes, e1.produces) == (("e1.txt",), (), ("a",))
    assert (e1.ran, e1.reason, e1.blocked_by) == (True, None, ())
    assert dict(e1.produced) == {"a": "one"}
    (artifact,) = e1.artifacts
    assert (artifact.path, artifact.size, artifact.reachable) == ("e1.txt", 3, True)


def test_an_element_that_did_not_pass_says_why(root: Path) -> None:
    _, e2, s, c = _report(root, first, second, gates).elements

    assert (e2.reason, e2.ran) == ("1 logs", True)
    assert (s.step, s.consumes, s.blocked_by, s.ran) == (
        f"{MODULE}.gates",
        ("a", "b"),
        ("e2",),
        False,
    )
    assert (c.step, c.designators, c.observes, c.produced) == (None, (), (), {})


def test_the_summary_counts_statuses_and_severities(root: Path) -> None:
    report = _report(root, first, second, gates)

    assert report.summary == Summary(elements=4, passed=1, failed=1, skipped=2)


def test_a_run_stopped_by_validation_lists_the_elements_with_their_bindings(root: Path) -> None:
    report = _report(root, first, second)  # s has no step (JP005), so e1 and e2 feed nothing

    assert report.verdict is Verdict.INVALID
    assert not report.ran
    assert [d.code for d in report.diagnostics] == ["JP005", "JP012", "JP012"]
    assert [(e.id, e.status, e.step) for e in report.elements] == [
        ("e1", None, f"{MODULE}.first"),
        ("e2", None, f"{MODULE}.second"),
        ("s", None, None),
        ("c", None, None),
    ]
    assert report.summary == Summary(elements=4, not_run=4, errors=3)


def test_a_strict_run_is_reported_as_strict(root: Path) -> None:
    @strategy("s", consumes=["a"])
    def ignores_b(a: str) -> Outcome:
        return Pass()

    report = _report(root, first, second, ignores_b, strict=True)

    assert report.strict
    assert {d.severity for d in report.diagnostics} == {Severity.ERROR}
    assert report.verdict is Verdict.INVALID


def test_a_refused_model_is_reported_without_elements() -> None:
    problem = Diagnostic("JP004", Severity.ERROR, "a cycle", element="a")

    report = RunReport.refused(InvalidJustificationError([problem]), strict=True)

    assert report == RunReport(None, Verdict.INVALID, (), (problem,), strict=True)
    assert report.summary == Summary(errors=1)
    assert not report.ran


def test_libraries_that_cannot_be_imported_are_reported_with_the_unbound_model() -> None:
    problem = Diagnostic("JP020", Severity.ERROR, "steps.py cannot be imported")

    report = RunReport.not_imported(RELEASE, LibraryLoadError([problem]))

    assert (report.justification, report.verdict, report.diagnostics) == (
        "m",
        Verdict.INVALID,
        (problem,),
    )
    assert report.elements == (
        ElementReport("e1", "e1", EVIDENCE, ("old:e1",), ("s",)),
        ElementReport("e2", "e2", EVIDENCE, (), ("s",)),
        ElementReport("s", "s", STRATEGY, (), ("c",)),
        ElementReport("c", "c", CONCLUSION, (), ()),
    )


def test_a_diagram_is_recorded_on_a_copy(root: Path) -> None:
    report = _report(root, first, second, gates)

    drawn = report.with_diagram("m.svg")

    assert (report.diagram, drawn.diagram) == (None, "m.svg")
    assert drawn.elements == report.elements


# --- Tracebacks ----------------------------------------------------------------------------


class ReleaseError(Exception):
    pass


@evidence("e1", observes={"log": "e1.txt"}, produces=["a"])
def broken(log: Path) -> Outcome:
    return Pass(a=str(1 / 0))


def test_a_step_that_raised_is_reported_with_its_trace(root: Path) -> None:
    (diagnostic, *_) = run(RELEASE, _registry(broken, second, gates), root=root).diagnostics
    report = RunReport(None, Verdict.FAIL, diagnostics=(diagnostic,), root=HERE)

    trace = report.trace(diagnostic)

    assert diagnostic.code == STEP_RAISED
    assert trace is not None
    assert (trace.exception, trace.message, trace.cause) == (
        "ZeroDivisionError",
        "division by zero",
        None,
    )
    (frame,) = trace.frames
    assert frame == Frame("test_report.py", frame.line, "broken", "return Pass(a=str(1 / 0))")
    assert f"at test_report.py, line {frame.line}" not in diagnostic.message  # run root differs


def test_an_exception_of_a_module_is_named_with_its_module() -> None:
    trace = Trace.of(user_traceback(_caught(ReleaseError("no release"))), HERE)

    assert (trace.exception, trace.message) == ("tests.unit.test_report.ReleaseError", "no release")


def _caught(error: BaseException) -> BaseException:
    try:
        raise error
    except BaseException as caught:
        return caught


def _chained(suppress: bool, explicit: bool) -> BaseException:
    try:
        try:
            raise KeyError("inner")
        except KeyError as inner:
            if suppress:
                raise ValueError("outer") from None
            if explicit:
                raise ValueError("outer") from inner
            raise ValueError("outer")  # noqa: B904
    except ValueError as outer:
        return outer


@pytest.mark.parametrize(
    ("suppress", "explicit", "cause"),
    [
        pytest.param(False, True, "KeyError", id="raised from"),
        pytest.param(False, False, "KeyError", id="raised while handling"),
        pytest.param(True, False, None, id="from None"),
    ],
)
def test_a_trace_keeps_the_exception_it_was_raised_from(
    suppress: bool, explicit: bool, cause: str | None
) -> None:
    trace = Trace.of(user_traceback(_chained(suppress, explicit)), HERE)

    assert trace.exception == "ValueError"
    assert (trace.cause.exception if trace.cause else None) == cause


def test_a_diagnostic_without_a_traceback_has_no_trace() -> None:
    diagnostic = Diagnostic("JP005", Severity.ERROR, "no step")

    assert RunReport(None, Verdict.INVALID, diagnostics=(diagnostic,)).trace(diagnostic) is None


def test_a_diagnostics_traceback_does_not_make_it_different() -> None:
    traced = Diagnostic(
        "JP022", Severity.ERROR, "raised", traceback=user_traceback(_caught(KeyError()))
    )

    assert traced == Diagnostic("JP022", Severity.ERROR, "raised")


@pytest.mark.parametrize(
    ("filename", "shown"),
    [
        pytest.param(str(HERE / "test_report.py"), "test_report.py", id="under the root"),
        pytest.param("/elsewhere/steps.py", "/elsewhere/steps.py", id="elsewhere"),
        pytest.param("<string>", "<string>", id="not a file"),
    ],
)
def test_a_path_is_shown_relative_to_the_root(filename: str, shown: str) -> None:
    assert shown_path(filename, HERE) == shown
