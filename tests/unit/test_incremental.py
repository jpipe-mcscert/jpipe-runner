"""Incremental runs: what changed since a report runs again, the rest is reused (#153, ADR-0039).

``tests/e2e/test_scenarios.py`` runs every scenario again with its golden report as the
baseline; these tests check each reason to run an element again, what a reused element
brings to the run, and the command line.
"""

import copy
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from jpipe_runner import Fail, Outcome, Pass, evidence, json_report, strategy
from jpipe_runner.cli import ExitCode, main
from jpipe_runner.engine import STEP_RAISED, RunResult, Verdict
from jpipe_runner.impact import InvalidReportError
from jpipe_runner.incremental import Baseline
from jpipe_runner.observables import Env, File, JsonValue
from jpipe_runner.report import RunReport
from jpipe_runner.steps import StepRegistry, step_of
from tests.anchored import run
from tests.scenarios import GOLDEN_FILE, SCENARIOS_ROOT
from tests.unit.validation.builders import CONCLUSION, EVIDENCE, STRATEGY, element, model

# e1 and e2 support s, which supports c.
MODEL = model(
    element("c", CONCLUSION),
    element("s", STRATEGY),
    element("e1", EVIDENCE),
    element("e2", EVIDENCE),
    relations=[("s", "c"), ("e1", "s"), ("e2", "s")],
)

Document = dict[str, Any]


class Library:
    """e1 produces the text of e1.txt, JSON; e2 produces the path of e2.txt, which a report
    holds only as its repr; s passes when it receives both. Each call is recorded."""

    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "e1.txt").write_text("one", encoding="utf-8")
        (root / "e2.txt").write_text("two", encoding="utf-8")
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def registry(self) -> StepRegistry:
        calls = self.calls

        @evidence("e1", observes={"log": "e1.txt"}, produces=["text"])
        def first(log: Path) -> Outcome:
            calls.append(("e1", {"log": log}))
            return Pass(text=log.read_text(encoding="utf-8"))

        @evidence("e2", observes={"log": "e2.txt"}, produces=["path"])
        def second(log: Path) -> Outcome:
            calls.append(("e2", {"log": log}))
            return Pass(path=log)

        @strategy("s", consumes=["text", "path"])
        def gates(text: str, path: Path) -> Outcome:
            calls.append(("s", {"text": text, "path": path}))
            return Pass() if text and path else Fail("nothing")

        steps = [step_of(f) for f in (first, second, gates)]
        return StepRegistry(step for step in steps if step is not None)

    def run(self, baseline: Baseline | None = None) -> tuple[RunResult, Document]:
        reuse = None if baseline is None else baseline.reuse
        result = run(MODEL, self.registry(), root=self.root, reuse=reuse)
        selection = None if baseline is None else baseline.selection
        return result, json_report.document(RunReport.of(result, self.root, selection))

    def called(self) -> list[str]:
        return [name for name, _ in self.calls]


@pytest.fixture
def library(tmp_path: Path) -> Library:
    return Library(tmp_path)


def _rerun(document: Document) -> dict[str, str]:
    selection = document["selection"]
    assert selection is not None
    rerun: dict[str, str] = selection["rerun"]
    return rerun


def _without_reuse(document: Document) -> Document:
    """``document`` without what says what an incremental run reused."""
    stripped = copy.deepcopy(document)
    stripped.pop("selection")
    for each in stripped["elements"]:
        each.pop("reused")
    return stripped


def test_with_nothing_changed_every_element_is_reused_as_the_baseline_reported_it(
    library: Library,
) -> None:
    _, first = library.run()
    library.calls.clear()

    result, again = library.run(Baseline("base.json", first, library.root))

    assert library.called() == []
    assert _rerun(again) == {}
    assert all(each["reused"] for each in again["elements"])
    assert _without_reuse(again) == _without_reuse(first)
    # A value held as JSON is passed on; one held as a repr is not: nothing consumes it.
    assert result.values.producers("text") == ("e1",)
    assert "path" not in result.values


def test_a_changed_file_reruns_its_evidence_and_everything_above_it(library: Library) -> None:
    _, first = library.run()
    (library.root / "e1.txt").write_text("changed", encoding="utf-8")
    library.calls.clear()

    _, again = library.run(Baseline("base.json", first, library.root))

    assert _rerun(again) == {
        "e1": "e1.txt changed",
        # s consumes the path e2 produced, which the report holds only as its repr.
        "e2": "s consumes 'path', which the baseline records only as its repr",
        "s": "e1 runs again",
        "c": "s runs again",
    }
    assert sorted(library.called()) == ["e1", "e2", "s"]


def test_a_value_the_baseline_holds_as_json_reaches_a_step_that_runs_again(
    library: Library,
) -> None:
    _, first = library.run()
    (library.root / "e2.txt").write_text("changed", encoding="utf-8")
    library.calls.clear()

    _, again = library.run(Baseline("base.json", first, library.root))

    assert list(_rerun(again)) == ["e2", "s", "c"]
    assert library.called() == ["e2", "s"]
    assert library.calls[-1] == ("s", {"text": "one", "path": library.root / "e2.txt"})
    assert again["elements"][0]["reused"] is True  # e1, first in topological order


def _element(document: Document, element_id: str) -> Document:
    return next(each for each in document["elements"] if each["id"] == element_id)


def _typed(first: Document) -> Document:
    """``first``, as if e1 had produced its text as a ``Text``, a ``str`` subclass."""
    return _changed(first, "e1", produced={"text": {"value": "one", "type": "steps.Text"}})


def test_a_value_json_reads_back_as_another_type_reruns_its_producer(
    library: Library,
) -> None:
    _, first = library.run()
    (library.root / "e2.txt").write_text("changed", encoding="utf-8")
    library.calls.clear()

    _, again = library.run(Baseline("base.json", _typed(first), library.root))

    assert _rerun(again)["e1"] == (
        "s consumes 'text', which the baseline records only as JSON, not as a steps.Text"
    )
    assert sorted(library.called()) == ["e1", "e2", "s"]


def test_a_reused_value_with_its_type_is_reported_with_it(library: Library) -> None:
    _, first = library.run()
    typed = _typed(first)

    result, again = library.run(Baseline("base.json", typed, library.root))

    assert library.called() == ["e1", "e2", "s"]  # the first run only
    assert _element(again, "e1")["produced"] == {"text": {"value": "one", "type": "steps.Text"}}
    assert "text" not in result.values  # it cannot reach a step as it was produced


def test_a_step_that_changes_a_reused_value_changes_nothing_reported(tmp_path: Path) -> None:
    for name in ("e1.txt", "e2.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    @evidence("e1", observes={"log": "e1.txt"}, produces=["names"])
    def first(log: Path) -> Outcome:
        return Pass(names=[log.name])

    @evidence("e2", observes={"log": "e2.txt"}, produces=["text"])
    def second(log: Path) -> Outcome:
        return Pass(text=log.read_text(encoding="utf-8"))

    @strategy("s", consumes=["names", "text"])
    def gates(names: list[str], text: str) -> Outcome:
        names.append(text)  # forbidden, but not prevented
        return Pass()

    steps = [step_of(f) for f in (first, second, gates)]
    registry = StepRegistry(step for step in steps if step is not None)
    base = json_report.document(RunReport.of(run(MODEL, registry, root=tmp_path), tmp_path))
    (tmp_path / "e2.txt").write_text("changed", encoding="utf-8")

    reused = run(MODEL, registry, root=tmp_path, reuse=Baseline("b", base, tmp_path).reuse)

    (e1,) = (each for each in reused.elements if each.element.id == "e1")
    assert e1.reused
    assert e1.produced == {"names": ["e1.txt"]}


def test_a_producer_that_recorded_no_value_is_reused(library: Library) -> None:
    _, first = library.run()
    failed = _changed(first, "e1", status="fail", reason="broken", produced={})
    (library.root / "e2.txt").write_text("changed", encoding="utf-8")
    library.calls.clear()

    _, again = library.run(Baseline("base.json", failed, library.root))

    assert _rerun(again) == {"e2": "e2.txt changed", "s": "e2 runs again", "c": "s runs again"}
    assert library.called() == ["e2"]  # s is not run: e1 did not pass
    assert _element(again, "s")["status"] == "skip"


def _changed(first: Document, element_id: str, **fields: Any) -> Document:
    changed = copy.deepcopy(first)
    for each in changed["elements"]:
        if each["id"] == element_id:
            each.update(fields)
    return changed


@pytest.mark.parametrize(
    ("fields", "why"),
    [
        pytest.param({"library_sha256": "0" * 64}, "its step's library changed", id="library"),
        pytest.param({"library_sha256": None}, "its step's library changed", id="no-library"),
        pytest.param({"produces": ["other"]}, "its step's declarations changed", id="produces"),
        pytest.param({"bound_to": "other.step"}, "its step's declarations changed", id="step"),
    ],
)
def test_a_step_that_is_not_the_one_the_baseline_ran_runs_again(
    library: Library, fields: dict[str, Any], why: str
) -> None:
    _, first = library.run()

    _, again = library.run(Baseline("base.json", _changed(first, "e2", **fields), library.root))

    assert _rerun(again) == {"e2": why, "s": "e2 runs again", "c": "s runs again"}


def test_what_cannot_be_checked_from_the_report_runs_again(library: Library) -> None:
    _, first = library.run()
    hidden = {
        "declared": "env:TOKEN",
        "variable": "TOKEN",
        "reachable": True,
        "hidden": True,
        "sha256": None,
        "value": None,
    }

    _, again = library.run(
        Baseline("base.json", _changed(first, "e2", observations=[hidden]), library.root)
    )

    assert _rerun(again)["e2"] == "env:TOKEN cannot be checked again"


def _renamed(first: Document) -> Document:
    return first | {"justification": "other"}


def _dry(first: Document) -> Document:
    return first | {"verdict": "valid"}


def _reshaped(first: Document) -> Document:
    return _changed(first, "e2", supports=[])


@pytest.mark.parametrize(
    ("baseline", "why"),
    [
        pytest.param(lambda first: None, "there is no baseline", id="none"),
        pytest.param(_dry, "the baseline ran no step", id="dry-run"),
        pytest.param(_renamed, "the baseline is a run of 'other'", id="other-justification"),
        pytest.param(_reshaped, "the model changed", id="other-model"),
    ],
)
def test_a_baseline_that_cannot_stand_for_the_run_reruns_everything(
    library: Library, baseline: Callable[[Document], Document | None], why: str
) -> None:
    _, first = library.run()
    library.calls.clear()

    _, again = library.run(Baseline("base.json", baseline(first), library.root))

    assert _rerun(again) == {"e1": why, "e2": why, "s": why, "c": why}
    assert sorted(library.called()) == ["e1", "e2", "s"]
    assert not any(each["reused"] for each in again["elements"])


def test_a_reused_element_brings_its_diagnostics_and_traceback_not_validation_s(
    tmp_path: Path,
) -> None:
    (tmp_path / "e1.txt").write_text("one", encoding="utf-8")

    @evidence("e1", observes={"log": "e1.txt"}, produces=["text"])
    def raises(log: Path) -> Outcome:
        raise RuntimeError(f"cannot read {log.name}")

    @evidence("e2", observes={"log": "absent.txt"}, produces=["path"])
    def unreachable(log: Path) -> Outcome:
        return Pass(path=log)

    @strategy("s", consumes=["text", "path"])
    def ignores(text: str, path: Path) -> Outcome:  # never reads them: JP027, a warning
        return Pass()

    steps = [step_of(f) for f in (raises, unreachable, ignores)]
    registry = StepRegistry(step for step in steps if step is not None)
    first = run(MODEL, registry, root=tmp_path)
    document = json_report.document(RunReport.of(first, tmp_path))

    baseline = Baseline("base.json", document, tmp_path)
    again = run(MODEL, registry, root=tmp_path, reuse=baseline.reuse)
    report = RunReport.of(again, tmp_path, baseline.selection)

    assert [d.code for d in again.diagnostics] == [d.code for d in first.diagnostics]
    raised = next(d for d in again.diagnostics if d.code == STEP_RAISED)
    assert raised.traceback is None
    recorded = next(d for d in first.diagnostics if d.code == STEP_RAISED)
    assert report.trace(raised) == RunReport.of(first, tmp_path).trace(recorded)
    assert again.result("e2").reached == first.result("e2").reached
    assert _without_reuse(json_report.document(report)) == _without_reuse(document)


def test_a_reused_element_keeps_what_it_observed_that_is_not_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SHOWN", "visible")
    monkeypatch.setenv("SECRET", "hidden")
    (tmp_path / "e1.json").write_text('{"version": "2.0"}', encoding="utf-8")

    @evidence(
        "e1",
        observes={"version": JsonValue("e1.json", "/version"), "shown": Env("SHOWN", True)},
        produces=["text"],
    )
    def first(version: str, shown: str) -> Outcome:
        return Pass(text=version + shown)

    @evidence("e2", observes={"secret": Env("SECRET"), "log": File("e1.json")}, produces=["path"])
    def second(secret: str, log: Path) -> Outcome:
        return Pass(path=log.name + secret)

    @strategy("s", consumes=["text", "path"])
    def gates(text: str, path: str) -> Outcome:
        return Pass() if text and path else Fail("nothing")

    steps = [step_of(f) for f in (first, second, gates)]
    registry = StepRegistry(step for step in steps if step is not None)
    document = json_report.document(RunReport.of(run(MODEL, registry, root=tmp_path), tmp_path))

    baseline = Baseline("base.json", document, tmp_path)
    again = run(MODEL, registry, root=tmp_path, reuse=baseline.reuse)
    report = json_report.document(RunReport.of(again, tmp_path, baseline.selection))

    # SECRET is hidden: e2, which observes it, runs again, and what is above it.
    assert _rerun(report) == {
        "e2": "env:SECRET cannot be checked again",
        "s": "e2 runs again",
        "c": "s runs again",
    }
    assert again.result("e1").reused
    assert _without_reuse(report) == _without_reuse(document)


def test_a_baseline_that_does_not_exist_is_none(tmp_path: Path) -> None:
    assert Baseline.read(str(tmp_path / "absent.json")).selection is None


def test_a_baseline_that_is_not_a_report_is_refused(tmp_path: Path) -> None:
    (tmp_path / "base.json").write_text("{}", encoding="utf-8")
    with pytest.raises(InvalidReportError):
        Baseline.read(str(tmp_path / "base.json"))


# --- The command line ------------------------------------------------------------------------


RELEASE = ["-l", "steps.py", "justification.json"]


@pytest.fixture
def release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workdir = tmp_path / "release"
    shutil.copytree(
        SCENARIOS_ROOT / "release_example",
        workdir,
        ignore=shutil.ignore_patterns("__pycache__", GOLDEN_FILE),
    )
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("NO_COLOR", "1")
    return workdir


def _main(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_the_command_line_reruns_what_changed_and_says_so(
    release: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(capsys, "--report", "base.json", *RELEASE)[0] == ExitCode.OK
    with (release / "mock" / "CHANGELOG.md").open("a", encoding="utf-8") as changelog:
        changelog.write("\n")

    code, out, _ = _main(capsys, "--incremental", "base.json", "--report", "base.json", *RELEASE)

    assert code == ExitCode.OK
    assert "# release:e1 (reused)\n" in out
    assert "  # release:e2\n" in out
    assert "incremental: 3 of 4 elements ran again, the rest reused from base.json\n" in out
    report = json.loads((release / "base.json").read_text(encoding="utf-8"))
    assert list(report["selection"]["rerun"]) == ["release:e2", "release:s", "release:c"]

    code, out, _ = _main(capsys, "--incremental", "base.json", *RELEASE)
    assert "incremental: nothing changed since base.json, every element reused\n" in out


def test_without_its_baseline_an_incremental_run_runs_everything(
    capsys: pytest.CaptureFixture[str], release: Path
) -> None:
    code, out, err = _main(capsys, "--incremental", "base.json", *RELEASE)

    assert code == ExitCode.OK
    assert "base.json does not exist: every element runs" in err
    assert "incremental: every element ran again (there is no baseline)\n" in out
    assert "(reused)" not in out


@pytest.mark.parametrize(
    ("argv", "problem"),
    [
        pytest.param(
            ["--incremental", "steps.py", *RELEASE], "--incremental steps.py is not a JSON report"
        ),
        pytest.param(
            ["--incremental", "base.json", "--dry-run", *RELEASE],
            "--incremental and --dry-run: a dry run calls no step, so reuses none",
        ),
        pytest.param(
            ["--incremental", "base.json", "--events", "base.json", *RELEASE],
            "--events base.json: the baseline, which the run reads",
        ),
    ],
)
def test_a_baseline_the_run_cannot_use_is_a_usage_error(
    capsys: pytest.CaptureFixture[str], release: Path, argv: list[str], problem: str
) -> None:
    _main(capsys, "--report", "base.json", *RELEASE)

    code, out, err = _main(capsys, *argv)

    assert code == ExitCode.USAGE
    assert out == ""
    assert problem in err


def test_a_baseline_that_cannot_be_read_exits_4(
    capsys: pytest.CaptureFixture[str], release: Path
) -> None:
    (release / "base.json").mkdir()

    code, out, _ = _main(capsys, "--incremental", "base.json", *RELEASE)

    assert code == ExitCode.IO
    assert out == ""


def test_a_skipped_element_is_reused_as_skipped(
    capsys: pytest.CaptureFixture[str], release: Path
) -> None:
    (release / "mock" / "junit.xml").write_text(
        '<testsuite tests="2" failures="1"/>', encoding="utf-8"
    )
    _main(capsys, "--report", "base.json", *RELEASE)

    code, out, _ = _main(capsys, "--incremental", "base.json", "--json", *RELEASE)

    assert code == ExitCode.FAILED
    report = json.loads(out)
    assert [(e["status"], e["reused"]) for e in report["elements"]] == [
        ("fail", True),
        ("pass", True),
        ("skip", True),
        ("skip", True),
    ]
    assert report["verdict"] == str(Verdict.FAIL)


_TYPED = """
from jpipe_runner import Pass, evidence

@evidence("e1", observes={"log": "e1.txt"}, produces=["text"])
def first(log):
    return Pass(text=str(log))
"""


@pytest.mark.parametrize(
    "filename",
    [
        pytest.param("<prompt>", id="typed-at-a-prompt"),
        pytest.param("absent/steps.py", id="file-gone"),
    ],
)
def test_a_step_whose_file_cannot_be_read_has_no_library_sha256(
    tmp_path: Path, filename: str
) -> None:
    namespace: dict[str, Any] = {}
    exec(compile(_TYPED, filename, "exec"), namespace)
    step = step_of(namespace["first"])
    assert step is not None
    assert step.library_sha256 is None

    planned = run(MODEL, StepRegistry([step]), root=tmp_path, dry_run=True)
    (first, *_) = json_report.document(RunReport.of(planned, tmp_path))["elements"]

    assert first["bound_to"] is not None
    assert first["library_sha256"] is None
