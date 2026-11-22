"""The command line, run in process (#124, ADR-0023).

Each test runs ``cli.main`` in a copy of a scenario, as its working directory, and reads
what it printed. The e2e scenarios run the same command in a subprocess, and pin each
report with a golden file; these tests cover the options, the outputs and the exit codes.
"""

import json
import logging
import os
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
from jpipe_runner.observables import fingerprint
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


def _exit_codes_in_help(help_text: str) -> list[str]:
    """The lines of the help's exit codes list, from its heading to the end."""
    return help_text[help_text.index("exit codes:\n") :].splitlines()[1:]


@pytest.mark.parametrize(
    ("command", "codes"),
    [([], [0, 1, 2, 3, 4]), (["impact"], [0, 2, 3, 4]), (["status"], [0, 1, 2, 3, 4])],
)
def test_the_help_lists_the_exit_codes_one_per_line(
    command: list[str], codes: list[int], capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _main(capsys, *command, "--help")

    assert code == ExitCode.OK
    listed = [
        line.split()[0]
        for line in _exit_codes_in_help(out)
        if line.startswith("  ") and line[2] != " "
    ]
    assert listed == [str(code) for code in codes]


def test_an_exit_code_too_long_for_the_terminal_wraps_under_its_meaning(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COLUMNS", "60")

    _, out, _ = _main(capsys, "--help")

    lines = _exit_codes_in_help(out)
    assert all(len(line) <= 60 for line in lines)
    assert lines[0].startswith("  0  the justification holds")
    assert lines[1].startswith("     ")  # the rest of 0's meaning, under its first word


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


def _noisy(release: Path) -> None:
    """Make the release's steps print, when imported and when run, and start a program
    that writes on its own stdout."""
    steps = release / "steps.py"
    source = steps.read_text(encoding="utf-8")
    source = source.replace(
        'RELEASE = "2.0"\n',
        'RELEASE = "2.0"\nprint("importing the release steps")\n',
    ).replace(
        "    suite = ElementTree.parse(report).getroot()\n",
        "    print('reading', report)\n"
        "    import subprocess, sys\n"
        "    subprocess.run([sys.executable, '-c', 'print(\"a program the step started\")'])\n"
        "    suite = ElementTree.parse(report).getroot()\n",
    )
    steps.write_text(source, encoding="utf-8")


def test_what_the_steps_write_goes_to_stderr_not_into_the_report(
    release: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _noisy(release)

    code = main(["--json", *RELEASE])
    out, err = capfd.readouterr()

    assert code == ExitCode.OK
    assert json.loads(out)["verdict"] == "pass"
    for printed in ("importing the release steps", "reading", "a program the step started"):
        assert printed in err


def test_what_the_steps_print_goes_to_stderr_without_a_stdout_to_redirect(
    release: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _noisy(release)

    def no_descriptor(fd: int) -> int:
        raise OSError(9, "Bad file descriptor")

    monkeypatch.setattr(os, "dup", no_descriptor)
    code, out, err = _main(capsys, "--json", "-l", "steps.py", "justification.json")

    assert code == ExitCode.OK
    assert json.loads(out)["verdict"] == "pass"
    assert "importing the release steps" in err


def test_stdout_is_left_alone_when_there_is_no_stderr_to_point_it_at(
    release: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    duplicated: list[int] = []
    closed: list[int] = []
    real_dup, real_dup2, real_close = os.dup, os.dup2, os.close

    def dup(fd: int) -> int:
        duplicated.append(real_dup(fd))
        return duplicated[-1]

    def no_stderr(fd: int, fd2: int, inheritable: bool = True) -> int:
        if (fd, fd2) == (2, 1):
            raise OSError(9, "Bad file descriptor")
        return real_dup2(fd, fd2, inheritable)

    def close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(os, "dup", dup)
    monkeypatch.setattr(os, "dup2", no_stderr)
    monkeypatch.setattr(os, "close", close)
    code, out, _ = _main(capsys, "--json", *RELEASE)

    assert code == ExitCode.OK
    assert json.loads(out)["verdict"] == "pass"
    assert duplicated[0] in closed  # the copy of stdout is not leaked


def test_impact_shows_nothing_a_library_prints_when_imported(
    release: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    _noisy(release)

    code = main(["impact", "--changed", "mock/junit.xml", *RELEASE])
    out, err = capfd.readouterr()

    assert code == ExitCode.OK
    assert "importing the release steps" not in out
    assert "importing the release steps" in err


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


def test_a_template_chain_naming_an_unknown_element_warns_and_is_drawn_flat(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    workdir = scenario("templated")
    path = workdir / "justification.json"
    compiled = json.loads(path.read_text(encoding="utf-8"))
    compiled["implements"]["elements"].append("readiness:gone")
    path.write_text(json.dumps(compiled), encoding="utf-8")
    argv = ["--diagram", "r.dot", "--json", "-l", "steps.py", "justification.json"]

    code, out, _ = _main(capsys, *argv)

    report = json.loads(out)
    assert code == ExitCode.OK
    assert report["verdict"] == "pass"
    assert [d["code"] for d in report["diagnostics"]] == ["JP026"]
    assert "subgraph" not in (workdir / "r.dot").read_text(encoding="utf-8")
    assert _main(capsys, "--strict", *argv)[0] == ExitCode.INVALID


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
        pytest.param(["--diagram", "release", *RELEASE], id="no suffix"),
        pytest.param(["--diagram", "mock", *RELEASE], id="a directory"),
        pytest.param(["--report", "mock", *RELEASE], id="a directory for the report"),
        pytest.param(["--diagram", "r.svg", "--report", "r.svg", *RELEASE], id="one file twice"),
        pytest.param(["--dataflow", "r.svg", *RELEASE], id="--dataflow, which --diagram replaced"),
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


# --- An output never overwrites what the run observes (#183) ---------------------------------


@pytest.mark.parametrize(
    ("flag", "observed", "step"),
    [
        pytest.param("--events", "mock/junit.xml", "the_test_suite_passes", id="events"),
        pytest.param("--report", "mock/CHANGELOG.md", "the_changelog_is_up_to_date", id="report"),
        pytest.param("--diagram", "mock/junit.xml", "the_test_suite_passes", id="diagram"),
    ],
)
@pytest.mark.parametrize("dry_run", [False, True], ids=["run", "dry run"])
def test_an_output_that_names_an_observed_file_is_refused_and_leaves_it_as_it_was(
    release: Path,
    capsys: pytest.CaptureFixture[str],
    flag: str,
    observed: str,
    step: str,
    dry_run: bool,
) -> None:
    if flag == "--diagram":  # its suffix must be a format
        (release / "mock" / "junit.dot").write_bytes((release / observed).read_bytes())
        observed = "mock/junit.dot"
        _observing(release, "junit.xml", "junit.dot")
    before = (release / observed).read_bytes()

    code, out, err = _main(capsys, *(["--dry-run"] if dry_run else []), flag, observed, *RELEASE)

    assert code == ExitCode.USAGE
    assert out == ""
    assert f"{flag} {observed}: {observed}, which steps.{step} observes" in err
    assert (release / observed).read_bytes() == before


def _observing(release: Path, old: str, new: str) -> None:
    """Make the release library observe ``new`` where it observes ``old``."""
    steps = release / "steps.py"
    steps.write_text(steps.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_an_output_a_glob_would_match_is_refused_before_it_exists(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _observing(release, '"mock/CHANGELOG.md"', '"mock/*.md"')

    code, _, err = _main(capsys, "--report", "mock/report.md", *RELEASE)

    assert code == ExitCode.USAGE
    assert "--report mock/report.md: mock/*.md, which steps.the_changelog_is_up_to_date" in err
    assert not (release / "mock" / "report.md").exists()


def test_an_events_file_the_run_created_is_removed_when_it_is_refused(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _observing(release, '"mock/CHANGELOG.md"', '"mock/*.jsonl"')
    (release / "mock" / "old.jsonl").write_text("{}\n", encoding="utf-8")

    code, _, _ = _main(capsys, "--events", "mock/run.jsonl", *RELEASE)

    assert code == ExitCode.USAGE
    assert not (release / "mock" / "run.jsonl").exists()


@pytest.mark.skipif(not hasattr(os, "link"), reason="no hard links here")
def test_an_output_that_links_to_an_observed_file_is_refused(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    os.link(release / "mock" / "junit.xml", release / "linked.json")

    code, _, err = _main(capsys, "--report", "linked.json", *RELEASE)

    assert code == ExitCode.USAGE
    assert "--report linked.json: mock/junit.xml, which steps.the_test_suite_passes" in err


def test_an_output_that_names_the_file_of_a_json_value_is_refused(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    directory = scenario("observables")
    before = (directory / "mock" / "package.json").read_bytes()

    code, _, err = _main(
        capsys, "--report", "mock/package.json", "-l", "checks/steps.py", "justification.json"
    )

    assert code == ExitCode.USAGE
    assert "--report mock/package.json: mock/package.json, which steps." in err
    assert (directory / "mock" / "package.json").read_bytes() == before


def test_a_step_bound_to_no_element_is_not_checked(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    steps = release / "steps.py"
    steps.write_text(
        steps.read_text(encoding="utf-8")
        + '\n\n@evidence("other:e", observes={"log": "elsewhere.log"}, produces=["x"])\n'
        + "def elsewhere(log):\n    return Pass(x=1)\n",
        encoding="utf-8",
    )

    code, _, err = _main(capsys, "--report", "elsewhere.log", *RELEASE)

    assert code != ExitCode.USAGE, err  # validation then refuses the library: JP015


def test_an_output_outside_the_root_is_not_taken_for_a_glob_s(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _observing(release, '"mock/CHANGELOG.md"', '"**/*.md"')

    code, _, err = _main(capsys, "--dry-run", "--report", "../outside.md", *RELEASE)

    assert code == ExitCode.OK, err


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symbolic links here")
def test_an_output_through_a_linked_directory_is_refused_before_it_exists(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _observing(release, '"mock/CHANGELOG.md"', '"mock/*.md"')
    (release / "build").symlink_to(release / "mock", target_is_directory=True)

    code, _, err = _main(capsys, "--report", "build/new.md", *RELEASE)

    assert code == ExitCode.USAGE
    assert "--report build/new.md: mock/*.md, which" in err
    assert not (release / "mock" / "new.md").exists()


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symbolic links here")
def test_an_output_a_glob_through_a_linked_directory_would_match_is_refused(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (release / "build").symlink_to(release / "mock", target_is_directory=True)
    _observing(release, '"mock/CHANGELOG.md"', '"build/*.md"')

    code, _, err = _main(capsys, "--report", "mock/new.md", *RELEASE)

    assert code == ExitCode.USAGE
    assert "--report mock/new.md: build/*.md, which" in err
    assert not (release / "mock" / "new.md").exists()


def test_a_previous_run_s_events_a_step_observes_are_put_back_when_refused(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _main(capsys, "--events", "mock/stage.jsonl", *RELEASE)
    before = (release / "mock" / "stage.jsonl").read_bytes()
    _observing(release, '"mock/CHANGELOG.md"', '"mock/stage.jsonl"')

    code, _, _ = _main(capsys, "--events", "mock/stage.jsonl", *RELEASE)

    assert code == ExitCode.USAGE
    assert (release / "mock" / "stage.jsonl").read_bytes() == before


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symbolic links here")
def test_a_refused_events_file_through_a_dangling_link_is_removed_and_the_link_kept(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _observing(release, '"mock/CHANGELOG.md"', '"mock/*.jsonl"')
    (release / "mock" / "old.jsonl").write_text("{}\n", encoding="utf-8")
    (release / "latest.jsonl").symlink_to(release / "mock" / "run.jsonl")

    code, _, _ = _main(capsys, "--events", "latest.jsonl", *RELEASE)

    assert code == ExitCode.USAGE
    assert (release / "latest.jsonl").is_symlink()
    assert not (release / "mock" / "run.jsonl").exists()


def test_a_refused_events_file_leaves_no_directory_behind(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _observing(release, '"mock/CHANGELOG.md"', '"new/**"')

    code, _, _ = _main(capsys, "--events", "new/dir/run.jsonl", *RELEASE)

    assert code == ExitCode.USAGE
    assert not (release / "new").exists()


def test_a_file_with_other_content_is_left_as_it_was_when_the_run_cannot_check_it(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (release / "notes.txt").write_text("not events\n", encoding="utf-8")
    (release / "justification.json").write_text("{", encoding="utf-8")  # refused: JP001

    code, _, err = _main(capsys, "--events", "notes.txt", *RELEASE)

    assert code == ExitCode.IO
    assert "notes.txt holds something other than a run's events" in err
    assert (release / "notes.txt").read_text(encoding="utf-8") == "not events\n"


def test_a_previous_run_s_events_are_emptied_at_once(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _main(capsys, "--events", "run.jsonl", *RELEASE)
    steps = release / "steps.py"
    steps.write_text(  # what the events file holds while the library is imported
        "from pathlib import Path\n"
        "Path('seen.jsonl').write_text(Path('run.jsonl').read_text(encoding='utf-8'),"
        " encoding='utf-8')\n" + steps.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    code, _, _ = _main(capsys, "--events", "run.jsonl", *RELEASE)

    seen = [json.loads(line)["event"] for line in (release / "seen.jsonl").read_text().splitlines()]
    assert code == ExitCode.OK
    assert seen == ["run.started"]  # this run's, not the previous run's


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="no named pipes here")
def test_events_go_to_a_named_pipe(release: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import threading

    os.mkfifo(release / "events.pipe")
    received: list[str] = []
    reader = threading.Thread(
        target=lambda: received.extend(
            (release / "events.pipe").read_text(encoding="utf-8").splitlines()
        )
    )
    reader.start()

    code, _, err = _main(capsys, "--events", "events.pipe", *RELEASE)
    reader.join(timeout=10)

    assert code == ExitCode.OK, err
    assert json.loads(received[0])["event"] == "run.started"
    assert json.loads(received[-1])["event"] == "run.ended"


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


def test_the_diagram_is_the_dataflow_drawn_and_recorded(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--diagram", "out/r.dot", "--report", "r.json"]

    code, out, _ = _main(capsys, *argv, *RELEASE)

    report = json.loads((release / "r.json").read_text(encoding="utf-8"))
    drawn = (release / "out" / "r.dot").read_text(encoding="utf-8")
    assert code == ExitCode.OK
    assert report["diagram"] == "out/r.dot"
    assert "dataflow" not in report
    assert "diagram: out/r.dot\nverdict: pass\n" in out
    assert drawn.startswith('digraph "release"')
    assert "variable tests_pass" in drawn


@needs_dot
def test_a_diagram_is_rendered_in_the_format_of_its_suffix(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, _ = _main(capsys, "--diagram", "release.SVG", *RELEASE)

    assert code == ExitCode.OK
    assert "<svg" in (release / "release.SVG").read_text(encoding="utf-8")


def test_an_output_whose_place_cannot_be_looked_at_exits_4(
    release: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    looked_at = Path.is_dir

    def is_dir(path: Path) -> bool:
        if path.name == "r.svg":
            raise PermissionError(13, "Permission denied", str(path))
        return looked_at(path)

    monkeypatch.setattr(Path, "is_dir", is_dir)

    code, out, err = _main(capsys, "--diagram", "locked/r.svg", *RELEASE)

    assert code == ExitCode.IO
    assert out == ""
    assert err == "jpipe-runner: error: locked/r.svg: Permission denied\n"


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
    before = _state(logger)

    _main(capsys, "-vv", *RELEASE)

    assert _state(logger) == before


def _state(logger: logging.Logger) -> tuple[int, bool, list[logging.Handler]]:
    return logger.level, logger.propagate, list(logger.handlers)


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


def test_impact_keeps_a_symbolic_link_under_the_working_directory_as_named(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = release.parent / "junit.xml"
    shutil.move(release / "mock" / "junit.xml", outside)
    (release / "mock" / "junit.xml").symlink_to(outside)

    code, out, err = _main(capsys, "impact", "--changed", "mock/../mock/junit.xml", *RELEASE)

    assert code == ExitCode.OK
    assert "  mock/junit.xml  release:e1\n" in out
    assert err == ""


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


def test_status_of_a_report_that_hides_what_was_observed_asks_for_a_new_run_and_is_1(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    scenario("observables")  # it observes PATH, which its report does not show
    library = ["--library", "checks/steps.py", "justification.json"]
    assert _main(capsys, "--report", "report.json", *library)[0] == ExitCode.OK

    code, out, _ = _main(capsys, "status", "report.json")

    assert code == ExitCode.FAILED
    assert "Information was hidden from the report, so it needs a new run:\n" in out
    assert "  env:PATH  environment\n" in out
    assert "still holds" not in out


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


def test_status_warns_of_missing_files_only_for_files(
    recorded: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A variable no longer set is a change, not a sign that status runs from the wrong
    directory: one file still there, one variable gone, and no warning."""
    document = json.loads((recorded / "report.json").read_text(encoding="utf-8"))
    kept = False
    for element in document["elements"]:
        if element["artifacts"] and not kept:
            element["artifacts"], kept = element["artifacts"][:1], True
            element["observations"] = [
                {
                    "declared": "env:JPIPE_RELEASE",
                    "variable": "JPIPE_RELEASE",
                    "reachable": True,
                    "hidden": False,
                    "sha256": fingerprint("1"),
                    "value": {"value": "1"},
                }
            ]
        else:
            element["artifacts"] = []
    (recorded / "report.json").write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.delenv("JPIPE_RELEASE", raising=False)

    code, out, err = _main(capsys, "status", "report.json")

    assert code == ExitCode.FAILED
    assert "env:JPIPE_RELEASE" in out
    assert "run status from the directory the run ran in" not in err


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


_SLUG_LIBRARY = """
from pathlib import Path

from jpipe_runner import JsonValue, Outcome, Pass, evidence, strategy


@evidence(
    "version",
    observes={"version": JsonValue("package.json", "POINTER"), "notes": "*.md"},
    produces=["announced"],
)
def announced(version: str, notes: list[Path]) -> Outcome:
    return Pass(announced=bool(notes))


@evidence("environment", observes={"notes": "notes.md"}, produces=["found"])
def found(notes: Path) -> Outcome:
    return Pass(found=notes.is_file())


@strategy("gates", consumes=["announced", "found"])
def gates(announced: bool, found: bool) -> Outcome:
    return Pass()
"""


def _slug(scenario: Callable[[str], Path], pointer: str = "/version") -> list[str]:
    """The observables example, with a library in app/[slug]/, a directory named as a
    Next.js route is, beside the files it observes. The arguments that name it."""
    root = scenario("observables")
    library = root / "app" / "[slug]"
    library.mkdir(parents=True)
    (library / "steps.py").write_text(_SLUG_LIBRARY.replace("POINTER", pointer), encoding="utf-8")
    (library / "package.json").write_text('{"version": "2.0"}', encoding="utf-8")
    (library / "notes.md").write_text("2.0\n", encoding="utf-8")
    return ["-l", "app/[[]slug]/steps.py", "justification.json"]


def test_a_library_in_a_directory_named_with_a_wildcard_observes_its_own_files(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """#167: the report escapes the directory's name, and impact and status match it."""
    library = _slug(scenario)
    assert _main(capsys, "--report", "report.json", *library)[0] == ExitCode.OK
    document = json.loads(Path("report.json").read_text(encoding="utf-8"))
    (version,) = (element for element in document["elements"] if element["id"] == "version")

    assert version["observes"] == ["app/[[]slug]/package.json", "app/[[]slug]/*.md"]
    assert [a["path"] for a in version["artifacts"]] == [
        "app/[slug]/package.json",
        "app/[slug]/notes.md",
    ]
    code, out, _ = _main(capsys, "impact", "--changed", "app/[slug]/notes.md", *library)
    assert (code, "  app/[slug]/notes.md  version, environment\n" in out) == (ExitCode.OK, True)
    assert _main(capsys, "status", "report.json")[:2] == (
        ExitCode.OK,
        "Justification: observables\n\n"
        "Everything the run observed is as it was: its report still holds.\n",
    )


def test_status_of_a_json_value_its_pointer_does_not_find_is_its_file_s_status(
    scenario: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """#166: the run read the file, so it has not appeared since."""
    library = _slug(scenario, "/versoin")
    assert _main(capsys, "--report", "report.json", *library)[0] == ExitCode.FAILED

    assert _main(capsys, "status", "report.json")[0] == ExitCode.OK
    Path("app/[slug]/package.json").write_text('{"versoin": "2.0"}', encoding="utf-8")
    code, out, _ = _main(capsys, "status", "report.json")
    assert (code, "  changed  app/[slug]/package.json  version\n" in out) == (
        ExitCode.FAILED,
        True,
    )


def test_a_justification_named_like_a_subcommand_is_run_when_not_first(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shutil.copy(release / "justification.json", release / "status")

    assert _main(capsys, "-l", "steps.py", "status")[0] == ExitCode.OK
    assert _main(capsys, "./status", "-l", "steps.py")[0] == ExitCode.OK
