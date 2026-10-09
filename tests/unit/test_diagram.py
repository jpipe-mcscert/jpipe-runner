"""Diagrams: the compiler's drawing of a justification, with what a run concluded (#123, #145,
ADR-0022).

The DOT text is checked as text, so these tests need no Graphviz. Only the tests that render
an image call ``dot``, and are skipped where it is not installed; CI installs it.
"""

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from jpipe_runner import Fail, Outcome, Pass, Skip, evidence, loader, strategy
from jpipe_runner.diagram import FORMATS, View, default_name, source, write
from jpipe_runner.engine import Verdict, run
from jpipe_runner.model import Element, Justification
from jpipe_runner.report import RunReport
from jpipe_runner.steps import StepRegistry, step_of
from tests.scenarios import discover
from tests.unit.validation.builders import CONCLUSION, EVIDENCE, STRATEGY, element, model

DOT = shutil.which("dot")
needs_dot = pytest.mark.skipif(DOT is None, reason="Graphviz's dot is not installed")

# Each scenario written in jPipe keeps the compiler's DOT next to its JSON:
# `jpipe process -i <model>.jd -m <name> -f DOT` (jPipe 2.5.0).
DRAWN = [scenario for scenario in discover() if (scenario.directory / "justification.dot").exists()]

RELEASE = model(
    element("c", CONCLUSION),
    element("s", STRATEGY),
    element("e1", EVIDENCE),
    element("e2", EVIDENCE),
    relations=[("s", "c"), ("e1", "s"), ("e2", "s")],
)


def test_four_scenarios_keep_the_compilers_diagram() -> None:
    assert {s.name for s in DRAWN} == {"release_example", "composed", "assembled", "unified"}


@pytest.mark.parametrize("scenario", DRAWN, ids=lambda scenario: scenario.name)
def test_a_justification_is_drawn_as_the_compiler_draws_it(scenario: Any) -> None:
    compiled = (scenario.directory / "justification.dot").read_text(encoding="utf-8")

    assert source(loader.load(scenario.justification)) == compiled


@pytest.mark.parametrize("scenario", DRAWN, ids=lambda scenario: scenario.name)
def test_a_run_in_which_nothing_ran_is_drawn_as_the_compiler_draws_it(scenario: Any) -> None:
    justification = loader.load(scenario.justification)
    report = RunReport.of(run(justification, StepRegistry([])))

    assert report.verdict is Verdict.INVALID
    assert source(justification, report) == (scenario.directory / "justification.dot").read_text(
        encoding="utf-8"
    )


def test_a_label_is_wrapped_and_escaped_as_the_compiler_does() -> None:
    label = 'The "release_candidate" passes every check the team wrote for it, twice'
    labelled = Justification("m", [Element("e", label, EVIDENCE)], [])

    (node,) = [line for line in source(labelled).splitlines() if line.startswith('  "e"')]

    assert node.startswith(
        '  "e" [label="The \\"release\\_candidate\\" passes every\\ncheck the team wrote for it,'
        ' twice", id="e", '
    )


# --- Statuses -------------------------------------------------------------------------------


def _steps(e1: Callable[[], Outcome], e2: Callable[[], Outcome]) -> StepRegistry:
    @evidence("e1", observes={"log": "e1.txt"}, produces=["a"])
    def first(log: Path) -> Outcome:
        return e1()

    @evidence("e2", observes={"logs": "*.log"}, produces=["b"])
    def second(logs: list[Path]) -> Outcome:
        return e2()

    @strategy("s", consumes=["a", "b"])
    def gates(a: str, b: str) -> Outcome:
        return Pass()

    return StepRegistry(s for s in map(step_of, (first, second, gates)) if s is not None)


def _drawn(
    root: Path,
    e1: Callable[[], Outcome],
    e2: Callable[[], Outcome] = lambda: Pass(b="b"),
    view: View = View.JUSTIFICATION,
) -> dict[str, str]:
    """The diagram's lines of a run of RELEASE, by node or edge."""
    (root / "e1.txt").write_text("one", encoding="utf-8")
    report = RunReport.of(run(RELEASE, _steps(e1, e2), root=root), root)
    lines = source(RELEASE, report, view=view).splitlines()
    return {line.strip().partition(" [")[0].rstrip(";"): line.strip() for line in lines}


def test_a_passing_element_keeps_its_style_with_a_green_border(tmp_path: Path) -> None:
    drawn = _drawn(tmp_path, lambda: Pass(a="a"))

    assert drawn['"e1"'] == (
        '"e1" [label="e1", id="e1", shape=note, style=filled, fillcolor="#9ECAE1", '
        'color="#009E73", penwidth=2, tooltip=pass];'
    )
    assert drawn['"e1" -> "s"'] == '"e1" -> "s" [color="#009E73"];'


def test_a_failed_element_is_vermillion_and_blocks_what_it_supports(tmp_path: Path) -> None:
    (tmp_path / "e2.log").write_text("two", encoding="utf-8")

    drawn = _drawn(tmp_path, lambda: Fail("two tests failed"))

    assert drawn['"e1"'] == (
        '"e1" [label="e1", id="e1", shape=note, style=filled, fillcolor="#D55E00", '
        'fontcolor=white, fontname="Helvetica-Bold", penwidth=2, '
        'tooltip="fail: two tests failed"];'
    )
    assert drawn['"e1" -> "s"'] == '"e1" -> "s" [color="#D55E00"];'
    assert drawn['"s"'] == (
        '"s" [label="s", id="s", shape=hexagon, style="filled,dashed", fillcolor="#EEEEEE", '
        'color="#999999", tooltip="skip: not run: e1 did not pass"];'
    )
    assert drawn['"s" -> "c"'] == '"s" -> "c" [color="#999999", style=dashed];'
    assert drawn['"c"'].endswith(
        'shape=rect, style="filled,rounded,dashed", fillcolor="#EEEEEE", color="#999999", '
        'tooltip="skip: not run: e1 did not pass"];'
    )


def test_an_element_that_skips_on_its_own_account_has_a_thicker_border(tmp_path: Path) -> None:
    drawn = _drawn(tmp_path, lambda: Skip("not today"))

    assert drawn['"e1"'].endswith('color="#999999", tooltip="skip: not today", penwidth=2];')
    assert "penwidth" not in drawn['"s"']


def test_a_report_of_another_justification_is_refused() -> None:
    other = RunReport("other", Verdict.PASS)

    with pytest.raises(ValueError, match="'other'"):
        source(RELEASE, other)


# --- The dataflow view ----------------------------------------------------------------------


def test_the_dataflow_view_adds_files_and_variables(tmp_path: Path) -> None:
    (tmp_path / "e2.log").write_text("two", encoding="utf-8")

    drawn = _drawn(tmp_path, lambda: Pass(a="a"), view=View.DATAFLOW)

    assert drawn['label="m (dataflow)"'] == 'label="m (dataflow)";'
    assert drawn['"artifact e1.txt"'] == (
        '"artifact e1.txt" [label="e1.txt", fontname=Courier, fontsize=10, shape=folder];'
    )
    assert drawn['"variable a"'] == (
        '"variable a" [label="a", fontname=Courier, fontsize=10, shape=ellipse];'
    )
    assert drawn['"artifact e1.txt" -> "e1"'] == (
        '"artifact e1.txt" -> "e1" [style=dotted, arrowhead=empty, label=" observes", fontsize=9];'
    )
    assert drawn['"e1" -> "variable a"'] == (
        '"e1" -> "variable a" [style=dashed, color="#0072B2", label=" produces", fontsize=9];'
    )
    assert drawn['"variable a" -> "s"'] == (
        '"variable a" -> "s" [style=dashed, color="#0072B2", label=" consumes", fontsize=9];'
    )


def test_a_file_that_could_not_be_reached_is_vermillion(tmp_path: Path) -> None:
    drawn = _drawn(tmp_path, lambda: Pass(a="a"), view=View.DATAFLOW)  # no *.log

    assert drawn['"artifact *.log"'].endswith('shape=folder, color="#D55E00", penwidth=2];')
    assert "color" not in drawn['"artifact e1.txt"']


def test_a_variable_that_was_not_produced_is_dashed(tmp_path: Path) -> None:
    (tmp_path / "e2.log").write_text("two", encoding="utf-8")

    drawn = _drawn(tmp_path, lambda: Fail("no"), view=View.DATAFLOW)

    assert drawn['"variable a"'].endswith('shape=ellipse, style=dashed, color="#999999"];')
    assert "style" not in drawn['"variable b"']


def test_a_variable_without_one_producer_and_a_consumer_is_vermillion() -> None:
    @evidence("e1", observes={"log": "e1.txt"}, produces=["a", "unread"])
    def first(log: Path) -> Outcome:
        return Pass()

    @evidence("e2", observes={"log": "e2.txt"}, produces=["a"])
    def second(log: Path) -> Outcome:
        return Pass()

    @strategy("s", consumes=["a", "missing"])
    def gates(a: str, missing: str) -> Outcome:
        return Pass()

    registry = StepRegistry(s for s in map(step_of, (first, second, gates)) if s is not None)
    report = RunReport.of(run(RELEASE, registry))  # invalid: JP009, JP010, JP011
    lines = source(RELEASE, report, view=View.DATAFLOW).splitlines()

    for name in ("a", "unread", "missing"):
        (node,) = [line for line in lines if line.startswith(f'  "variable {name}" [')]
        assert node.endswith('color="#D55E00", penwidth=2];')


# --- Writing a diagram ----------------------------------------------------------------------


def test_the_default_name_is_the_justifications() -> None:
    assert default_name(RELEASE, "svg") == "m.svg"
    assert default_name(RELEASE, "png", View.DATAFLOW) == "m-dataflow.png"


def test_the_dot_format_is_written_without_graphviz(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")

    written = write(tmp_path / "out" / "m.dot", RELEASE)

    assert written.read_text(encoding="utf-8") == source(RELEASE)


def test_a_format_can_be_named_whatever_the_suffix(tmp_path: Path) -> None:
    written = write(tmp_path / "m.txt", RELEASE, fmt="DOT")

    assert written.read_text(encoding="utf-8") == source(RELEASE)


def test_an_unknown_format_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="'bmp'"):
        write(tmp_path / "m.bmp", RELEASE)


def test_without_graphviz_a_rendered_format_says_to_install_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")

    with pytest.raises(FileNotFoundError, match="install Graphviz"):
        write(tmp_path / "m.svg", RELEASE)


def test_a_failure_of_graphviz_is_an_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "Error: syntax error\n")

    monkeypatch.setattr(subprocess, "run", failing)

    with pytest.raises(OSError, match="syntax error"):
        write(tmp_path / "m.png", RELEASE)


@needs_dot
@pytest.mark.parametrize("fmt", [fmt for fmt in FORMATS if fmt != "dot"])
def test_every_format_is_rendered_by_graphviz(tmp_path: Path, fmt: str) -> None:
    written = write(tmp_path / "out" / f"m.{fmt}", RELEASE)

    assert written.stat().st_size > 0


@needs_dot
def test_an_svg_keeps_the_ids_and_the_statuses(tmp_path: Path) -> None:
    (tmp_path / "e1.txt").write_text("one", encoding="utf-8")
    report = RunReport.of(
        run(RELEASE, _steps(lambda: Fail("no"), lambda: Pass(b="b")), root=tmp_path)
    )

    svg = ElementTree.parse(write(tmp_path / "m.svg", RELEASE, report)).getroot()

    namespace = {"svg": "http://www.w3.org/2000/svg"}
    nodes = {g.get("id"): g for g in svg.iterfind(".//svg:g[@class='node']", namespace)}
    assert set(nodes) == {"c", "s", "e1", "e2"}
    fills = {
        node_id: {p.get("fill") for p in g.iterfind(".//svg:polygon", namespace)}
        for node_id, g in nodes.items()
    }
    assert "#d55e00" in {fill.lower() for fill in fills["e1"] if fill}
