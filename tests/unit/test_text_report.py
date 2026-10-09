"""The text report: a run laid out for a terminal, in the manner of Cucumber (#121)."""

import io
from pathlib import Path
from typing import Any

import pytest

from jpipe_runner.artifacts import Observation
from jpipe_runner.diagnostics import Diagnostic, Severity, user_traceback
from jpipe_runner.engine import Status, Verdict
from jpipe_runner.model import Kind
from jpipe_runner.report import ElementReport, RunReport
from jpipe_runner.steps import Artifact
from jpipe_runner.text_report import render, use_colour, use_unicode
from tests.unit.validation.builders import CONCLUSION, EVIDENCE, STRATEGY

HERE = Path(__file__).parent
JUNIT = Artifact("report", "mock/junit.xml")


def _element(element_id: str, kind: Kind, label: str, **fields: Any) -> ElementReport:
    return ElementReport(element_id, label, kind, **fields)


E1_FAILED = _element(
    "release:e1",
    EVIDENCE,
    "The test suite passes",
    status=Status.FAIL,
    reason="mock/junit.xml: 2 tests failed",
    ran=True,
    step="steps.the_test_suite_passes",
    artifacts=(Observation(JUNIT, "mock/junit.xml", "f757d068913c" + "0" * 52, 187),),
)
E2_PASSED = _element(
    "release:e2",
    EVIDENCE,
    "The changelog is up to date",
    status=Status.PASS,
    ran=True,
    step="steps.the_changelog_is_up_to_date",
)
S_BLOCKED = _element(
    "release:s",
    STRATEGY,
    "All release gates pass",
    status=Status.SKIP,
    reason="not run: release:e1 did not pass",
    blocked_by=("release:e1",),
    step="steps.all_release_gates_pass",
)
C_BLOCKED = _element(
    "release:c",
    CONCLUSION,
    "Version 2.0 is ready to ship",
    status=Status.SKIP,
    reason="not run: release:e1 did not pass",
    blocked_by=("release:e1",),
)
FAILED = RunReport("release", Verdict.FAIL, (E1_FAILED, E2_PASSED, S_BLOCKED, C_BLOCKED))


def test_a_run_is_one_line_per_element_then_the_summary_and_the_verdict() -> None:
    assert render(FAILED) == (
        "Justification: release\n"
        "  Version 2.0 is ready to ship\n"
        "\n"
        "  ✘ Evidence    The test suite passes         # release:e1\n"
        "      steps.the_test_suite_passes: mock/junit.xml: 2 tests failed\n"
        "      observed mock/junit.xml (sha256 f757d068913c…, 187 bytes)\n"
        "  ✔ Evidence    The changelog is up to date   # release:e2\n"
        "  - Strategy    All release gates pass        # release:s\n"
        "      not run: release:e1 did not pass\n"
        "  - Conclusion  Version 2.0 is ready to ship  # release:c\n"
        "      not run: release:e1 did not pass\n"
        "\n"
        "4 elements (1 failed, 2 skipped, 1 passed)\n"
        "verdict: fail\n"
    )


def test_without_unicode_the_symbols_are_ascii() -> None:
    text = render(FAILED, unicode=False)

    assert "  x Evidence" in text
    assert "  + Evidence" in text
    assert "(sha256 f757d068913c..., 187 bytes)" in text
    assert text.isascii()


def test_colour_paints_each_element_and_the_verdict_by_status() -> None:
    text = render(FAILED, colour=True)

    assert "\033[31m  ✘ Evidence" in text
    assert "\033[32m  ✔ Evidence" in text
    assert "\033[36m  - Strategy" in text
    assert "\033[31mverdict: fail\033[0m" in text
    assert "\033[" not in render(FAILED)


def test_an_unreachable_artifact_of_a_failed_evidence_is_named() -> None:
    unreachable = Observation(JUNIT, "mock/junit.xml")
    failed = _element(
        "e1", EVIDENCE, "Tests pass", status=Status.FAIL, reason="missing", artifacts=(unreachable,)
    )

    text = render(RunReport("m", Verdict.FAIL, (failed,)))

    assert "      observed mock/junit.xml (unreachable)\n" in text


def test_a_step_that_skips_or_fails_without_a_reason_says_so() -> None:
    skipped = _element("e1", EVIDENCE, "Tests pass", status=Status.SKIP, ran=True, step="s.f")

    text = render(RunReport("m", Verdict.SKIP, (skipped,)))

    assert "      s.f: no reason given\n" in text
    assert text.endswith("1 element (1 skipped)\nverdict: skip\n")


def test_a_long_label_pushes_its_id() -> None:
    long = _element("e1", EVIDENCE, "x" * 60, status=Status.PASS)
    short = _element("e2", EVIDENCE, "y", status=Status.PASS)

    text = render(RunReport("m", Verdict.PASS, (long, short)))

    assert f"  ✔ Evidence  {'x' * 60}  # e1\n" in text
    assert f"  ✔ Evidence  {'y':<50}  # e2\n" in text


def test_diagnostics_come_before_the_summary_each_with_its_fix() -> None:
    warning = Diagnostic("JP024", Severity.WARNING, "dropped", element="e1", fix="Declare it.")
    passed = _element("e1", EVIDENCE, "Tests pass", status=Status.PASS)

    text = render(RunReport("m", Verdict.PASS, (passed,), (warning,)), colour=True)

    assert text.endswith(
        "\033[33mJP024 warning [e1]: dropped\033[0m\n"
        "  fix: Declare it.\n"
        "\n"
        "1 element (1 passed)\n"
        "1 diagnostic (1 warning)\n"
        "\033[32mverdict: pass\033[0m\n"
    )


def test_a_run_in_which_nothing_ran_shows_only_its_diagnostics() -> None:
    problem = Diagnostic("JP005", Severity.ERROR, "no step", element="s")
    not_run = _element("s", STRATEGY, "Gates", step=None)

    text = render(RunReport("m", Verdict.INVALID, (not_run,), (problem, problem), strict=True))

    assert text == (
        "Justification: m\n"
        "\n"
        "JP005 error [s]: no step\n"
        "JP005 error [s]: no step\n"
        "\n"
        "2 diagnostics (2 errors)\n"
        "strict: warnings count as errors\n"
        "verdict: invalid (nothing ran)\n"
    )


def test_a_dry_run_says_that_no_step_was_called() -> None:
    not_run = _element("s", STRATEGY, "Gates", step="steps.gates")

    assert render(RunReport("m", Verdict.VALID, (not_run,))) == (
        "Justification: m\n\nverdict: valid (a dry run: no step was called)\n"
    )


def test_a_refused_model_has_no_header() -> None:
    problem = Diagnostic("JP001", Severity.ERROR, "not JSON")

    assert render(RunReport(None, Verdict.INVALID, diagnostics=(problem,))) == (
        "JP001 error: not JSON\n\n1 diagnostic (1 error)\nverdict: invalid (nothing ran)\n"
    )


def _raised_from() -> BaseException:
    try:
        try:
            {}["missing"]
        except KeyError as inner:
            raise RuntimeError("the step is broken") from inner
    except RuntimeError as outer:
        return outer


def test_an_exception_is_shown_with_its_traceback_and_cause() -> None:
    trace = user_traceback(_raised_from())
    raised = Diagnostic("JP022", Severity.ERROR, "the step raised", element="e1", traceback=trace)

    text = render(RunReport(None, Verdict.FAIL, diagnostics=(raised,), root=HERE))

    lines = text.splitlines()
    start = lines.index("  Traceback (most recent call last):")
    assert lines[start + 1].startswith('    File "test_text_report.py", line ')
    assert lines[start + 1].endswith(", in _raised_from")
    assert lines[start + 2] == '      raise RuntimeError("the step is broken") from inner'
    assert lines[start + 3] == "  RuntimeError: the step is broken"
    assert lines[start + 4] == "  Caused by:"
    assert lines[start + 6].endswith(", in _raised_from")
    assert lines[start + 8] == "  KeyError: 'missing'"


class _Stream(io.StringIO):
    def __init__(self, tty: bool, encoding: str | None = "utf-8") -> None:
        super().__init__()
        self._tty, self._encoding = tty, encoding

    def isatty(self) -> bool:
        return self._tty

    @property
    def encoding(self) -> str | None:  # type: ignore[override]
        return self._encoding


@pytest.mark.parametrize(
    ("tty", "environ", "coloured"),
    [
        pytest.param(True, {}, True, id="a terminal"),
        pytest.param(False, {}, False, id="a pipe"),
        pytest.param(True, {"NO_COLOR": "1"}, False, id="NO_COLOR"),
        pytest.param(True, {"NO_COLOR": ""}, True, id="NO_COLOR empty"),
    ],
)
def test_colour_is_for_a_terminal_unless_the_environment_refuses_it(
    tty: bool, environ: dict[str, str], coloured: bool
) -> None:
    assert use_colour(_Stream(tty), environ) is coloured


def test_a_closed_stream_is_not_coloured() -> None:
    stream = io.StringIO()
    stream.close()

    assert use_colour(stream, {}) is False


@pytest.mark.parametrize(
    ("encoding", "unicode"),
    [
        pytest.param("utf-8", True, id="utf-8"),
        pytest.param("cp1252", False, id="cp1252"),
        pytest.param(None, False, id="no encoding"),
        pytest.param("no-such-codec", False, id="unknown"),
    ],
)
def test_symbols_are_unicode_when_the_stream_can_encode_them(
    encoding: str | None, unicode: bool
) -> None:
    assert use_unicode(_Stream(False, encoding)) is unicode
