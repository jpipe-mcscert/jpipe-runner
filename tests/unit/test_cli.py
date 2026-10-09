"""The command line, run in process (#124, ADR-0023).

Each test runs ``cli.main`` in a copy of a scenario, as its working directory, and reads
what it printed. The e2e scenarios run the same command in a subprocess, and pin each
report with a golden file; these tests cover the options, the outputs and the exit codes.
"""

import json
import logging
import runpy
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from jpipe_runner import __version__, diagram, impact, json_report, loader
from jpipe_runner.cli import ExitCode, exit_code, main
from jpipe_runner.engine import Verdict, run
from jpipe_runner.libraries import imported
from jpipe_runner.report import RunReport
from jpipe_runner.steps import StepRegistry
from tests.scenarios import GOLDEN_FILE, SCENARIOS_ROOT, Scenario, discover

VALIDATOR = Draft202012Validator(json_report.SCHEMA)
RELEASE = ["-l", "steps.py", "justification.json"]
needs_dot = pytest.mark.skipif(
    shutil.which("dot") is None, reason="Graphviz's dot is not installed"
)

Run = tuple[int, str, str]


@pytest.fixture
def scenario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], Path]:
    """Copy a scenario, and make the copy the working directory."""

    def copy(name: str) -> Path:
        workdir = tmp_path / name
        shutil.copytree(
            SCENARIOS_ROOT / name,
            workdir,
            ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
        )
        monkeypatch.chdir(workdir)
        monkeypatch.delenv("NO_COLOR", raising=False)
        return workdir

    return copy


@pytest.fixture
def release(scenario: Callable[[str], Path]) -> Path:
    return scenario("release_example")


def _main(capsys: pytest.CaptureFixture[str], *argv: str) -> Run:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


# --- Exit codes ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verdict", "strict", "code"),
    [
        (Verdict.PASS, False, ExitCode.OK),
        (Verdict.PASS, True, ExitCode.OK),
        (Verdict.VALID, False, ExitCode.OK),
        (Verdict.SKIP, False, ExitCode.OK),
        (Verdict.SKIP, True, ExitCode.FAILED),
        (Verdict.FAIL, False, ExitCode.FAILED),
        (Verdict.INVALID, False, ExitCode.INVALID),
    ],
)
def test_the_exit_code_follows_the_verdict(verdict: Verdict, strict: bool, code: ExitCode) -> None:
    assert exit_code(verdict, strict=strict) is code


def test_the_exit_codes_are_those_ci_scripts_rely_on() -> None:
    assert [int(code) for code in ExitCode] == [0, 1, 2, 3, 4]


@pytest.mark.parametrize("case", discover(), ids=lambda case: case.name)
def test_every_scenario_exits_as_it_expects_with_a_report_that_matches_the_schema(
    case: Scenario, scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    scenario(case.name)

    code, out, _ = _main(capsys, *case.command()[3:])  # without `python -m jpipe_runner`

    assert code == case.exit_code
    VALIDATOR.validate(json.loads(out))


# --- The report ----------------------------------------------------------------------------


def test_a_run_prints_the_text_report_and_nothing_on_stderr(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _main(capsys, *RELEASE)

    assert code == ExitCode.OK
    assert out.startswith("Justification: release\n")
    assert out.endswith("verdict: pass\n")
    assert err == ""


def test_json_prints_the_json_report_of_the_run(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    justification = loader.load("justification.json")
    with imported(["steps.py"]) as modules:
        result = run(justification, StepRegistry.from_modules(modules))
    expected = json_report.dumps(RunReport.of(result))

    code, out, _ = _main(capsys, "--json", *RELEASE)

    assert code == ExitCode.OK
    assert out == expected


def test_report_writes_the_json_report_while_stdout_shows_the_text(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _main(capsys, "--report", "out/report.json", *RELEASE)

    written = (release / "out" / "report.json").read_text(encoding="utf-8")
    assert code == ExitCode.OK
    assert out.startswith("Justification: release\n")
    assert json.loads(written)["verdict"] == "pass"


def test_report_and_json_write_the_same_report(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = _main(capsys, "--json", "--report", "report.json", *RELEASE)

    assert (release / "report.json").read_text(encoding="utf-8") == out


def test_a_report_that_cannot_be_written_exits_4_after_printing_the_report(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _main(capsys, "--report", "steps.py/report.json", *RELEASE)

    assert code == ExitCode.IO
    assert out.endswith("verdict: pass\n")
    assert "cannot write the report" in err


# --- Running -------------------------------------------------------------------------------


def test_strict_fails_a_skipped_justification(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    scenario("skip_scenario")

    assert _main(capsys, "-l", "steps.py", "justification.json")[0] == ExitCode.OK
    assert _main(capsys, "--strict", "-l", "steps.py", "justification.json")[0] == ExitCode.FAILED


def test_strict_counts_a_warning_as_an_error(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    scenario("composed")
    libraries = ["-l", "draft_steps.py", "-l", "tested_steps.py", "justification.json"]

    assert _main(capsys, *libraries)[0] == ExitCode.OK
    assert _main(capsys, "--strict", *libraries)[0] == ExitCode.INVALID


def test_a_dry_run_is_valid_and_calls_no_step(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (release / "mock" / "junit.xml").unlink()  # a run would fail e1 (JP019)

    code, out, _ = _main(capsys, "--dry-run", "--json", *RELEASE)

    report = json.loads(out)
    assert code == ExitCode.OK
    assert report["verdict"] == "valid"
    assert {(e["status"], e["ran"]) for e in report["elements"]} == {(None, False)}


def test_a_dry_run_of_a_library_that_does_not_validate_is_invalid(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    scenario("missing_producer")

    code, out, _ = _main(capsys, "--dry-run", "-l", "steps.py", "justification.json")

    assert code == ExitCode.INVALID
    assert out.endswith("verdict: invalid (nothing ran)\n")


def test_libraries_can_be_named_by_a_glob(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    scenario("composed")

    code, _, err = _main(capsys, "-vv", "-l", "*_steps.py", "justification.json")

    assert code == ExitCode.OK
    assert "step libraries: ['draft_steps.py', 'tested_steps.py']" in err


def test_a_jpipe_source_file_is_refused_with_a_fix(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _main(capsys, "-l", "steps.py", "release.jd")

    assert code == ExitCode.INVALID
    assert "jpipe process -f JSON" in out


# --- Inputs that cannot be read ------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "problem"),
    [
        pytest.param(["-l", "steps.py", "missing.json"], "missing.json", id="no justification"),
        pytest.param(["-l", "steps.py", "mock"], "mock", id="a directory as justification"),
        pytest.param(["-l", "nothing.py", "justification.json"], "nothing.py", id="no library"),
        pytest.param(
            ["-l", "no*.py", "justification.json"], "no*.py", id="a glob matching nothing"
        ),
        pytest.param(["-p", "steps.py", *RELEASE], "steps.py", id="a python path not a directory"),
    ],
)
def test_an_input_that_cannot_be_read_exits_4_without_a_report(
    argv: list[str], problem: str, release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _main(capsys, *argv)

    assert code == ExitCode.IO
    assert out == ""
    assert err.startswith("jpipe-runner: error: ")
    assert problem in err


# --- Usage ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["justification.json"], id="no library"),
        pytest.param(["--diagram", "release.txt", *RELEASE], id="a suffix that is no format"),
        pytest.param(["--dataflow", "release", *RELEASE], id="no suffix"),
        pytest.param(["--diagram", "mock", *RELEASE], id="a directory"),
        pytest.param(["--report", "mock", *RELEASE], id="a directory for the report"),
        pytest.param(["--diagram", "r.svg", "--dataflow", "r.svg", *RELEASE], id="one file twice"),
        pytest.param(["-v", "-q", *RELEASE], id="verbose and quiet"),
        pytest.param(["-v", "name:value", *RELEASE], id="v3's --variable"),
        pytest.param(["--colour", "red", *RELEASE], id="an unknown colour choice"),
    ],
)
def test_a_wrong_command_line_exits_2_before_anything_runs(
    argv: list[str], release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _main(capsys, *argv)

    assert code == ExitCode.USAGE
    assert out == ""
    assert "usage: jpipe-runner" in err


def test_version_prints_the_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert _main(capsys, "--version") == (ExitCode.OK, f"jpipe-runner {__version__}\n", "")


def test_main_reads_the_process_arguments(
    release: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["jpipe-runner", *RELEASE])

    assert main() == ExitCode.OK
    assert capsys.readouterr().out.endswith("verdict: pass\n")


def test_python_m_drops_the_working_directory_from_the_python_path(
    release: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["jpipe-runner", "--version"])
    monkeypatch.setattr(sys, "path", [str(release), *sys.path])
    monkeypatch.delitem(sys.modules, "jpipe_runner.__main__", raising=False)

    with pytest.raises(SystemExit) as stop:
        runpy.run_module("jpipe_runner", run_name="__main__")

    assert stop.value.code == ExitCode.OK
    assert str(release) not in sys.path
    assert capsys.readouterr().out == f"jpipe-runner {__version__}\n"


# --- Diagrams ------------------------------------------------------------------------------


def test_both_diagrams_are_drawn_and_recorded(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--diagram", "out/r.dot", "--dataflow", "out/r-flow.dot", "--report", "r.json"]

    code, out, _ = _main(capsys, *argv, *RELEASE)

    report = json.loads((release / "r.json").read_text(encoding="utf-8"))
    assert code == ExitCode.OK
    assert (report["diagram"], report["dataflow"]) == ("out/r.dot", "out/r-flow.dot")
    assert "diagram: out/r.dot\ndataflow: out/r-flow.dot\nverdict: pass\n" in out
    assert (release / "out" / "r.dot").read_text(encoding="utf-8").startswith('digraph "release"')
    assert "variable tests_pass" in (release / "out" / "r-flow.dot").read_text(encoding="utf-8")


@needs_dot
def test_a_diagram_is_rendered_in_the_format_of_its_suffix(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, _ = _main(capsys, "--diagram", "release.SVG", *RELEASE)

    assert code == ExitCode.OK
    assert "<svg" in (release / "release.SVG").read_text(encoding="utf-8")


def test_without_graphviz_nothing_runs_for_a_diagram_that_needs_it(
    release: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    code, out, err = _main(capsys, "--diagram", "release.svg", *RELEASE)

    assert code == ExitCode.IO
    assert out == ""
    assert "Graphviz's dot is needed to draw release.svg" in err


def test_without_graphviz_a_dot_file_is_still_written(
    release: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)

    assert _main(capsys, "--diagram", "release.dot", *RELEASE)[0] == ExitCode.OK
    assert (release / "release.dot").is_file()


def test_a_diagram_that_fails_to_draw_exits_4_with_the_report(
    release: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: Path, *args: object, **options: object) -> Path:
        raise OSError(f"dot failed to draw {path}: syntax error")

    monkeypatch.setattr(diagram, "write", broken)

    code, out, err = _main(capsys, "--json", "--diagram", "release.dot", *RELEASE)

    assert code == ExitCode.IO
    assert json.loads(out)["diagram"] is None
    assert "dot failed to draw release.dot" in err


def test_the_diagram_of_a_refused_model_is_not_drawn(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    workdir = scenario("circular_dependency")

    code, _, err = _main(capsys, "--diagram", "c.dot", "-l", "steps.py", "justification.json")

    assert code == ExitCode.INVALID
    assert not (workdir / "c.dot").exists()
    assert "the model was refused, so c.dot is not drawn" in err


# --- Logging and colour --------------------------------------------------------------------


def test_verbose_logs_what_the_runner_does(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, err = _main(capsys, "-v", *RELEASE)

    assert "jpipe-runner: info: loaded release from justification.json: 4 elements\n" in err
    assert f"steps run with Python {sys.executable}" in err
    assert "jpipe-runner: info: pass release:e1" in err
    assert "debug" not in err


def test_very_verbose_logs_details_with_the_logger_names(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, err = _main(capsys, "-vv", *RELEASE)

    assert "jpipe-runner: debug: jpipe_runner.engine: calling steps.the_test_suite_passes" in err
    assert (
        "jpipe-runner: debug: jpipe_runner.libraries: imported steps.py as the module steps" in err
    )
    assert "jpipe-runner: debug: jpipe_runner.cli: sys.path: " in err


def test_quiet_hides_warnings(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    scenario("circular_dependency")
    argv = ["--diagram", "c.dot", "-l", "steps.py", "justification.json"]

    assert "warning" in _main(capsys, *argv)[2]
    assert _main(capsys, "-q", *argv)[2] == ""


def test_quiet_still_logs_errors(release: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, _, err = _main(capsys, "-q", "-l", "steps.py", "missing.json")

    assert err.startswith("jpipe-runner: error: ")


def test_logging_is_restored_after_a_run(release: Path, capsys: pytest.CaptureFixture[str]) -> None:
    logger = logging.getLogger("jpipe_runner")
    before = (logger.level, logger.propagate, list(logger.handlers))

    _main(capsys, "-vv", *RELEASE)

    assert (logger.level, logger.propagate, list(logger.handlers)) == before


@pytest.mark.parametrize(
    ("choice", "no_colour", "coloured"),
    [
        ("auto", None, False),  # capsys is not a terminal
        ("always", None, True),
        ("always", "1", True),  # an explicit choice overrides NO_COLOR
        ("never", None, False),
    ],
)
def test_colour_is_chosen_by_the_option(
    choice: str,
    no_colour: str | None,
    coloured: bool,
    release: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if no_colour is not None:
        monkeypatch.setenv("NO_COLOR", no_colour)

    _, out, _ = _main(capsys, "--colour", choice, *RELEASE)

    assert ("\033[" in out) is coloured


# --- impact --------------------------------------------------------------------------------


def test_impact_lists_what_a_changed_file_reaches(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _main(capsys, "impact", "--changed", "mock/junit.xml", *RELEASE)

    assert code == ExitCode.OK
    assert "  mock/junit.xml  release:e1\n" in out
    assert out.endswith(
        "Affected (3 elements):\n"
        "  Evidence    The test suite passes         # release:e1\n"
        "  Strategy    All release gates pass        # release:s\n"
        "  Conclusion  Version 2.0 is ready to ship  # release:c\n"
    )


def test_impact_calls_no_step(release: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (release / "mock" / "junit.xml").unlink()  # a step that ran would fail

    code, _, err = _main(capsys, "impact", "-v", "--changed", "mock/junit.xml", *RELEASE)

    assert code == ExitCode.OK
    assert "a dry run calls no step" in err


def test_impact_takes_absolute_paths_and_leaves_out_those_outside(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    junit = str(release / "mock" / "junit.xml")
    outside = str(release.parent / "elsewhere.txt")

    code, out, err = _main(capsys, "impact", "--changed", junit, "--changed", outside, *RELEASE)

    assert code == ExitCode.OK
    assert "  mock/junit.xml  release:e1\n" in out
    assert "elsewhere.txt is outside the working directory, and is left out" in err


def test_impact_without_declarations_shows_why_and_exits_3(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    scenario("import_error")

    code, out, _ = _main(
        capsys, "impact", "--changed", "steps.py", "-l", "steps.py", "justification.json"
    )

    assert code == ExitCode.INVALID
    assert "JP020 error" in out


def test_impact_since_a_revision_asks_git(
    release: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    def changed_since(ref: str, root: Path = Path()) -> list[str]:
        asked.append(ref)
        return ["mock/CHANGELOG.md"]

    monkeypatch.setattr(impact, "changed_since", changed_since)

    code, out, _ = _main(capsys, "impact", "--since", "origin/main", *RELEASE)

    assert (code, asked) == (ExitCode.OK, ["origin/main"])
    assert "  mock/CHANGELOG.md  release:e2\n" in out


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="no change"),
        pytest.param(["--changed", "a", "--since", "HEAD"], id="both"),
        pytest.param(["--since=--output=x"], id="an option as a revision"),
    ],
)
def test_impact_needs_one_kind_of_change(
    argv: list[str], release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _main(capsys, "impact", *argv, *RELEASE)

    assert code == ExitCode.USAGE
    assert "usage: jpipe-runner impact" in err


# --- status --------------------------------------------------------------------------------


@pytest.fixture
def recorded(release: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """The release example, with the JSON report of a run that passed."""
    assert _main(capsys, "--report", "report.json", *RELEASE)[0] == ExitCode.OK
    return release


def test_status_of_unchanged_files_is_0(recorded: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _main(capsys, "status", "report.json")

    assert code == ExitCode.OK
    assert out.endswith("its report still holds.\n")


def test_status_of_a_changed_file_lists_what_is_stale_and_is_1(
    recorded: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (recorded / "mock" / "CHANGELOG.md").write_text("2.1\n", encoding="utf-8")

    code, out, _ = _main(capsys, "status", "report.json")

    assert code == ExitCode.FAILED
    assert "  changed  mock/CHANGELOG.md  release:e2\n" in out
    assert "Stale (3 elements):\n" in out


def test_status_from_another_directory_warns(
    recorded: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(recorded / "mock")

    code, _, err = _main(capsys, "status", "../report.json")

    assert code == ExitCode.FAILED
    assert "run status from the directory the run ran in" in err


def test_status_of_a_dry_run_is_3(release: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _main(capsys, "--dry-run", "--report", "report.json", *RELEASE)

    code, _, err = _main(capsys, "status", "report.json")

    assert code == ExitCode.INVALID
    assert "no step ran" in err


def test_status_of_a_file_that_is_not_a_report_is_3(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, err = _main(capsys, "status", "justification.json")

    assert code == ExitCode.INVALID
    assert "is not a JSON report" in err


def test_status_of_a_missing_report_is_4(release: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _main(capsys, "status", "missing.json")[0] == ExitCode.IO


def test_a_justification_named_like_a_subcommand_is_run_when_not_first(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copy(release / "justification.json", release / "status")

    assert _main(capsys, "-l", "steps.py", "status")[0] == ExitCode.OK
    assert _main(capsys, "./status", "-l", "steps.py")[0] == ExitCode.OK
