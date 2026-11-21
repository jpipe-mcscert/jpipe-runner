"""The events of a run, ``--events`` (#169, ADR-0030).

Every scenario runs with ``--events`` and ``--report``, and its events must preview its
report: the same elements, the same diagnostics, the same verdict, each element decided
after the elements that support it. The other tests cover what a stream says of a run that
does not run its steps, how it measures time, and what happens when it cannot be written.
"""

import io
import json
import logging
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO

import pytest
from jsonschema import Draft202012Validator

from jpipe_runner import cli, diagram, engine, events, json_report
from jpipe_runner.cli import ExitCode, main
from jpipe_runner.engine import ElementResult, RunResult, Status
from jpipe_runner.events import EventStream
from jpipe_runner.model import Element, Justification, Kind
from jpipe_runner.steps import StepRegistry
from tests.scenarios import (
    GOLDEN_FILE,
    REFUSED_LIBRARIES,
    REFUSED_MODELS,
    SCENARIOS_ROOT,
    Scenario,
    discover,
)
from tests.streams import of, read
from tests.unit.validation.builders import CONCLUSION, element, model

EVENTS = "out/run.jsonl"
needs_dot = pytest.mark.skipif(
    shutil.which("dot") is None, reason="Graphviz's dot is not installed"
)
RELEASE = ["-l", "steps.py", "justification.json"]


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str], Path]:
    """Copy a scenario, and make the copy the working directory."""

    def copy(name: str) -> Path:
        directory = tmp_path / name
        shutil.copytree(
            SCENARIOS_ROOT / name,
            directory,
            ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
        )
        monkeypatch.chdir(directory)
        return directory

    return copy


def _arguments(scenario: Scenario) -> list[str]:
    arguments = []
    for library in scenario.libraries:
        arguments += ["--library", library]
    for path in scenario.python_path:
        arguments += ["--python-path", path]
    return [*arguments, "justification.json"]


def _canonical(items: list[dict[str, Any]]) -> list[str]:
    return sorted(json.dumps(item, sort_keys=True) for item in items)


@pytest.mark.parametrize("scenario", discover(), ids=lambda scenario: scenario.name)
def test_the_events_of_every_scenario_preview_its_report(
    scenario: Scenario,
    workdir: Callable[[str], Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = workdir(scenario.name)

    code = main(["--events", EVENTS, "--report", "report.json", *_arguments(scenario)])

    capsys.readouterr()
    found = read(directory / EVENTS)
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    assert [event["seq"] for event in found] == list(range(len(found)))
    started, ended = found[0], found[-1]
    assert (started["event"], ended["event"]) == ("run.started", "run.ended")
    assert started["justification"] == report["justification"]
    assert started["elements"] == [e["id"] for e in report["elements"]]
    assert (ended["verdict"], ended["summary"]) == (report["verdict"], report["summary"])
    assert ended["exit_code"] == code == scenario.exit_code
    assert ended["report"] == "report.json"

    validated = of(found, "validation.ended")
    refused = scenario.name in REFUSED_MODELS or scenario.name in REFUSED_LIBRARIES
    assert len(validated) == (0 if refused else 1)
    decided = of(found, "element.decided")
    ran = report["verdict"] not in ("invalid", "valid")
    assert _canonical([event["element"] for event in decided]) == (
        _canonical(report["elements"]) if ran else []
    )
    if not refused:
        streamed = [d for event in [*validated, *decided] for d in event["diagnostics"]]
        assert _canonical(streamed) == _canonical(report["diagnostics"])
    # The diagram is drawn before the first step exactly when the steps run, and Graphviz
    # can draw it; it is gone once the run has ended.
    previewed = of(found, "diagram.drawn")
    assert len(previewed) == (1 if ran and shutil.which("dot") else 0)
    for event in previewed:
        assert not Path(event["path"]).exists()
        first = min(e["seq"] for e in found if e["event"].startswith("element."))
        assert validated[0]["seq"] < event["seq"] < first


@pytest.mark.parametrize("scenario", discover(), ids=lambda scenario: scenario.name)
def test_an_element_is_started_then_decided_after_its_supporters(
    scenario: Scenario,
    workdir: Callable[[str], Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = workdir(scenario.name)

    main(["--events", EVENTS, *_arguments(scenario)])

    capsys.readouterr()
    found = read(directory / EVENTS)
    decided = {event["element"]["id"]: event for event in of(found, "element.decided")}
    supporters: dict[str, set[str]] = {element_id: set() for element_id in decided}
    for event in decided.values():
        for supported in event["element"]["supports"]:
            supporters[supported].add(event["element"]["id"])
    for element_id, event in decided.items():
        assert all(decided[s]["seq"] < event["seq"] for s in supporters[element_id])
    started = {event["id"]: event["seq"] for event in of(found, "element.started")}
    # Started: bound, and every supporter passed, so that its step is called unless an
    # artifact it observes cannot be reached.
    assert started.keys() == {
        element_id
        for element_id, event in decided.items()
        if event["element"]["bound_to"] is not None and not event["element"]["blocked_by"]
    }
    assert all(seq < decided[element_id]["seq"] for element_id, seq in started.items())


def test_the_schema_is_valid_and_names_its_versions() -> None:
    Draft202012Validator.check_schema(events.SCHEMA)
    started = events.SCHEMA["$defs"]["run.started"]["properties"]
    assert started["schema_version"] == {"const": events.SCHEMA_VERSION}
    assert started["report_schema_version"]["const"] == json_report.SCHEMA_VERSION


def test_a_dry_run_streams_its_start_its_validation_and_its_end(
    workdir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    directory = workdir("release_example")

    assert main(["--dry-run", "--events", EVENTS, *RELEASE]) == ExitCode.OK

    found = read(directory / EVENTS)
    assert [event["event"] for event in found] == ["run.started", "validation.ended", "run.ended"]
    assert found[0]["dry_run"] is True
    assert (found[-1]["verdict"], found[-1]["report"]) == ("valid", None)


def test_a_refused_model_streams_its_start_and_its_end(
    workdir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    directory = workdir("circular_dependency")

    assert main(["--events", EVENTS, *RELEASE]) == ExitCode.INVALID

    started, ended = read(directory / EVENTS)
    assert (started["justification"], started["elements"]) == (None, [])
    assert (ended["verdict"], ended["exit_code"]) == ("invalid", ExitCode.INVALID)


@pytest.fixture
def temporary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The directory the command line's temporary directories are made in, for a test to
    see what is left in it."""
    directory = tmp_path / "tmp"
    directory.mkdir()
    made = tempfile.mkdtemp
    monkeypatch.setattr(
        cli.tempfile, "mkdtemp", lambda **options: made(**{**options, "dir": directory})
    )
    return directory


def _drawings(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, str]]:
    """Each diagram the command line draws, in order: where, and its DOT text."""
    drawn: list[tuple[Path, str]] = []
    write = cli.diagram.write

    def recorded(path: Path, model: Justification, report: Any = None, **options: Any) -> Path:
        written = write(path, model, report, **options)
        assert path.exists()
        drawn.append((path, diagram.source(model, report)))
        return written

    monkeypatch.setattr(cli.diagram, "write", recorded)
    return drawn


@needs_dot
def test_with_events_the_diagram_is_drawn_before_the_first_step_and_then_deleted(
    workdir: Callable[[str], Path],
    temporary: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = workdir("release_example")
    drawn = _drawings(monkeypatch)

    main(["--dry-run", "--diagram", "dry.dot", *RELEASE])
    main(["--events", EVENTS, *RELEASE])

    (_, dry), (preview, previewed) = drawn
    assert previewed == dry
    assert (preview.name, preview.parent.parent) == ("diagram.svg", temporary)
    found = read(directory / EVENTS)
    assert [e["event"] for e in found][:4] == [
        "run.started",
        "validation.ended",
        "diagram.drawn",
        "element.started",
    ]
    assert of(found, "diagram.drawn")[0]["path"] == str(preview)
    assert found[-1]["diagram"] is None
    assert list(temporary.iterdir()) == []
    assert not list(directory.glob("*.svg"))


@needs_dot
def test_the_diagram_file_holds_only_the_run_s_own_diagram(
    workdir: Callable[[str], Path],
    temporary: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = workdir("release_example")
    drawn = _drawings(monkeypatch)

    main(["--events", EVENTS, "--diagram", "release.dot", *RELEASE])

    (preview, _), (final, text) = drawn
    assert preview.parent.parent == temporary
    assert final == Path("release.dot")
    assert (directory / "release.dot").read_text(encoding="utf-8") == text
    assert read(directory / EVENTS)[-1]["diagram"] == "release.dot"


def test_a_dry_run_announces_no_preview(
    workdir: Callable[[str], Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = workdir("release_example")
    drawn = _drawings(monkeypatch)

    main(["--dry-run", "--events", EVENTS, "--diagram", "release.dot", *RELEASE])

    assert [path for path, _ in drawn] == [Path("release.dot")]
    assert of(read(directory / EVENTS), "diagram.drawn") == []


def test_without_events_no_preview_is_drawn(
    workdir: Callable[[str], Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir("release_example")
    drawn = _drawings(monkeypatch)

    main(["--diagram", "release.dot", *RELEASE])

    assert [path for path, _ in drawn] == [Path("release.dot")]


def test_without_graphviz_no_preview_is_drawn_and_the_run_goes_on(
    workdir: Callable[[str], Path],
    temporary: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = workdir("release_example")
    monkeypatch.setattr(shutil, "which", lambda name: None)

    code = main(["--events", EVENTS, *RELEASE])

    assert code == ExitCode.OK
    assert of(read(directory / EVENTS), "diagram.drawn") == []
    assert "not drawn before the steps run: Graphviz's dot is not installed" in (
        capsys.readouterr().err
    )
    assert list(temporary.iterdir()) == []


@needs_dot
@pytest.mark.parametrize(
    "raised",
    [
        pytest.param(OSError("dot failed to draw diagram.svg: out of memory"), id="OSError"),
        pytest.param(
            UnicodeEncodeError("ascii", "✔", 0, 1, "ordinal not in range(128)"),
            id="anything else",
        ),
    ],
)
def test_a_preview_that_cannot_be_drawn_is_logged_and_changes_nothing_else(
    workdir: Callable[[str], Path],
    temporary: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    raised: Exception,
) -> None:
    directory = workdir("release_example")

    def failing(*arguments: Any, **options: Any) -> Path:
        raise raised

    monkeypatch.setattr(cli.diagram, "write", failing)

    code = main(["--events", EVENTS, *RELEASE])

    assert code == ExitCode.OK
    assert of(read(directory / EVENTS), "diagram.drawn") == []
    assert "warning: cannot draw the diagram before the steps run: " in capsys.readouterr().err
    assert list(temporary.iterdir()) == []


@needs_dot
def test_the_preview_is_deleted_however_the_run_ends(
    workdir: Callable[[str], Path],
    temporary: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = workdir("release_example")

    def unprintable(*arguments: Any) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(cli, "_print", unprintable)

    code = main(["--events", EVENTS, *RELEASE])

    assert code == ExitCode.IO
    assert len(of(read(directory / EVENTS), "diagram.drawn")) == 1
    assert list(temporary.iterdir()) == []


def test_the_diagram_is_named_at_the_end(
    workdir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    directory = workdir("release_example")

    main(["--events", EVENTS, "--diagram", "release.dot", *RELEASE])

    assert read(directory / EVENTS)[-1]["diagram"] == "release.dot"


def test_an_events_file_that_cannot_be_opened_exits_4_before_anything_runs(
    workdir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    workdir("release_example")

    code = main(["--events", "justification.json/run.jsonl", *RELEASE])

    out, err = capsys.readouterr()
    assert code == ExitCode.IO
    assert out == ""
    assert "justification.json" in err


@pytest.mark.parametrize(
    ("argv", "started"),
    [
        pytest.param(["-l", "steps.py", "missing.json"], False, id="no justification"),
        pytest.param(["-l", "nothing.py", "justification.json"], True, id="no library"),
    ],
)
def test_an_input_that_cannot_be_read_ends_the_stream_without_run_ended(
    workdir: Callable[[str], Path],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    started: bool,
) -> None:
    directory = workdir("release_example")

    assert main(["--events", EVENTS, *argv]) == ExitCode.IO

    found = read(directory / EVENTS)
    assert [event["event"] for event in found] == (["run.started"] if started else [])


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--events", "mock"], "--events mock: a directory, where a file is expected"),
        (["--events", "out.json", "--report", "out.json"], "--report and --events both write"),
        (
            ["--events", "justification.json"],
            "--events justification.json: the justification, which the run reads",
        ),
        (["--report", "./steps.py"], "--report steps.py: a step library, which the run reads"),
        (
            ["-l", "*.py", "--events", "steps.py"],
            "--events steps.py: a step library, which the run reads",
        ),
    ],
)
def test_an_output_another_output_writes_or_the_run_reads_is_a_usage_error(
    workdir: Callable[[str], Path],
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    message: str,
) -> None:
    workdir("release_example")

    assert main([*argv, *RELEASE]) == ExitCode.USAGE
    assert message in capsys.readouterr().err


def test_an_output_that_links_to_an_input_is_a_usage_error(
    workdir: Callable[[str], Path], capsys: pytest.CaptureFixture[str]
) -> None:
    directory = workdir("release_example")
    os.link(directory / "justification.json", directory / "link.json")

    assert main(["--events", "link.json", *RELEASE]) == ExitCode.USAGE
    assert "--events link.json: the justification" in capsys.readouterr().err
    assert (directory / "link.json").read_text(encoding="utf-8").startswith("{")


class _Failing(io.StringIO):
    """A file that takes ``lines`` lines, then fails to write."""

    def __init__(self, lines: int) -> None:
        super().__init__()
        self._lines = lines

    def write(self, text: str) -> int:
        if self._lines == 0:
            raise OSError(28, "No space left on device")
        self._lines -= 1
        return super().write(text)


def test_a_stream_that_cannot_be_written_stops_and_says_so_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    file = _Failing(lines=1)
    stream = EventStream(file)
    lonely = model(element("c", CONCLUSION))

    stream.run_started(lonely, strict=False, dry_run=False)
    stream.element_started(lonely.element("c"))
    stream.element_started(lonely.element("c"))

    assert stream.failed
    assert len(file.getvalue().splitlines()) == 1
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert [r.getMessage() for r in errors] == [
        "cannot write the run's events: No space left on device"
    ]


def _planned() -> RunResult:
    lonely = model(element("c", CONCLUSION))
    return engine.run(lonely, StepRegistry(()), dry_run=True)


def test_a_preview_that_draws_nothing_is_not_announced() -> None:
    file = io.StringIO()
    asked: list[RunResult] = []
    stream = EventStream(file, preview=lambda planned: asked.append(planned))

    stream.steps_starting(_planned())

    assert len(asked) == 1
    assert file.getvalue() == ""


def test_a_stream_that_failed_draws_no_preview() -> None:
    asked: list[RunResult] = []
    stream = EventStream(_Failing(lines=0), preview=lambda planned: asked.append(planned))
    lonely = model(element("c", CONCLUSION))
    stream.run_started(lonely, strict=False, dry_run=False)

    stream.steps_starting(_planned())

    assert stream.failed
    assert asked == []


class _Faulty:
    """The events file, which takes ``lines`` lines, then fails to write, and to close."""

    def __init__(self, file: TextIO, lines: int) -> None:
        self._file = file
        self._lines = lines

    def write(self, text: str) -> int:
        if self._lines == 0:
            raise OSError(28, "No space left on device")
        self._lines -= 1
        return self._file.write(text)

    def flush(self) -> None:
        self._file.flush()

    def close(self) -> None:
        self._file.close()
        if self._lines == 0:
            raise OSError(28, "No space left on device")


def test_a_run_whose_stream_fails_still_reports_and_exits_4(
    workdir: Callable[[str], Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workdir("release_example")
    monkeypatch.setattr(
        cli,
        "EventStream",
        lambda file, root, preview: EventStream(_Faulty(file, lines=2), root=root, preview=preview),
    )

    code = main(["--events", EVENTS, *RELEASE])

    out, err = capsys.readouterr()
    assert code == ExitCode.IO
    assert "verdict: pass" in out
    assert err.count("cannot write the run's events") == 1


class _Unprintable(io.StringIO):
    def write(self, text: str) -> int:
        raise OSError(28, "No space left on device")


def test_a_report_that_cannot_be_printed_ends_the_stream_without_run_ended(
    workdir: Callable[[str], Path],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = workdir("release_example")
    monkeypatch.setattr(sys, "stdout", _Unprintable())

    assert main(["--events", EVENTS, *RELEASE]) == ExitCode.IO

    assert "run.ended" not in [event["event"] for event in read(directory / EVENTS)]


def test_elapsed_time_is_measured_from_the_opening_in_milliseconds() -> None:
    ticks = iter([10.0, 10.0, 10.2504])
    file = io.StringIO()
    stream = EventStream(file, clock=lambda: next(ticks))
    lonely = model(element("c", CONCLUSION))

    stream.run_started(lonely, strict=False, dry_run=False)
    stream.element_started(lonely.element("c"))

    assert [json.loads(line)["elapsed_ms"] for line in file.getvalue().splitlines()] == [0, 250]


def test_an_event_is_one_line_of_utf_8_whatever_its_text_holds() -> None:
    file = io.StringIO()
    stream = EventStream(file)
    # A lone surrogate is what a file name that is not UTF-8 decodes to.
    label = "two\nlines\x85and\u2028three\u2029é\udcff"
    breaking = Justification("m", [Element("c", label, Kind.CONCLUSION)], [])
    stream.run_started(breaking, strict=False, dry_run=False)
    result = ElementResult(breaking.element("c"), Status.SKIP, reason="nothing\nsupports it")

    stream.element_decided(result)

    lines = file.getvalue().splitlines()
    assert len(lines) == 2
    assert "é" in lines[1]
    lines[1].encode("utf-8")
    decided = json.loads(lines[1])["element"]
    assert decided["label"] == label
    assert decided["reason"] == "nothing\nsupports it"


def test_an_element_decided_before_the_run_started_is_a_runner_bug() -> None:
    stream = EventStream(io.StringIO())
    decided = ElementResult(model(element("c", CONCLUSION)).element("c"), Status.SKIP)

    with pytest.raises(RuntimeError, match="runner bug"):
        stream.element_decided(decided)
