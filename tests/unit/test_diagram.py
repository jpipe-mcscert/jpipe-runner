"""The diagram: the dataflow of a justification, in the compiler's notation, with what a run
concluded (#123, #145, ADR-0029).

The DOT text is checked as text, so these tests need no Graphviz. Only the tests that render
an image call ``dot``, and are skipped where it is not installed; CI installs it.
"""

import os
import shutil
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from jpipe_runner import (
    Env,
    Fail,
    Outcome,
    Pass,
    Produced,
    Skip,
    conclusion,
    diagram,
    engine,
    evidence,
    loader,
    strategy,
)
from jpipe_runner.diagram import FORMATS, source, write
from jpipe_runner.engine import Verdict
from jpipe_runner.libraries import imported
from jpipe_runner.model import Element, Justification, Template, TemplateChain
from jpipe_runner.report import RunReport
from jpipe_runner.steps import StepRegistry, step_of
from tests.anchored import run
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    STRATEGY,
    SUB_CONCLUSION,
    element,
    model,
)

DOT = shutil.which("dot")
needs_dot = pytest.mark.skipif(DOT is None, reason="Graphviz's dot is not installed")

RELEASE = model(
    element("c", CONCLUSION),
    element("s", STRATEGY),
    element("e1", EVIDENCE),
    element("e2", EVIDENCE),
    relations=[("s", "c"), ("e1", "s"), ("e2", "s")],
)


def test_without_a_report_the_argument_is_drawn_alone_in_the_compilers_notation() -> None:
    assert source(RELEASE) == (
        'digraph "m" {\n'
        "  rankdir=BT;\n"
        '  label="m";\n'
        '  "c" [label="c", id="c", shape=rect, style="filled,rounded", fillcolor=lightgrey];\n'
        '  "s" [label="s", id="s", shape=hexagon, style=filled, fillcolor="#F0C27F"];\n'
        '  "e1" [label="e1", id="e1", shape=note, style=filled, fillcolor="#9ECAE1"];\n'
        '  "e2" [label="e2", id="e2", shape=note, style=filled, fillcolor="#9ECAE1"];\n'
        '  "s" -> "c";\n'
        '  "e1" -> "s";\n'
        '  "e2" -> "s";\n'
        "}\n"
    )


def test_a_label_is_wrapped_and_escaped_as_the_compiler_does() -> None:
    label = 'The "release_candidate" passes every check the team wrote for it, twice'
    labelled = Justification("m", [Element("e", label, EVIDENCE)], [])

    (node,) = [line for line in source(labelled).splitlines() if line.startswith('  "e" [')]

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
) -> dict[str, str]:
    """The diagram's lines of a run of RELEASE, by node or edge."""
    (root / "e1.txt").write_text("one", encoding="utf-8")
    report = RunReport.of(run(RELEASE, _steps(e1, e2), root=root), root)
    lines = source(RELEASE, report).splitlines()
    return {line.strip().partition(" [")[0].rstrip(";"): line.strip() for line in lines}


def _marked(symbol: str | None, text: str, size: int = 20) -> str:
    """The HTML-like label of a node drawn with a report: ``text`` beside the cell of its
    symbol, at ``size`` points, which holds ``symbol``, or nothing."""
    width, height = (28, 32) if size == 20 else (22, 22)
    held = "" if symbol is None else f'<font point-size="{size}">{symbol}</font>'
    return (
        '<<table border="0" cellborder="0" cellspacing="0"><tr>'
        f'<td fixedsize="true" width="{width}" height="{height}">{held}</td>'
        f"<td>{text}</td></tr></table>>"
    )


def test_a_passing_element_keeps_its_style_with_a_green_border_and_a_check_mark(
    tmp_path: Path,
) -> None:
    (tmp_path / "e2.log").write_text("two", encoding="utf-8")

    drawn = _drawn(tmp_path, lambda: Pass(a="a"))

    assert drawn['"e1"'] == (
        f'"e1" [label={_marked("✔", "e1")}, id="e1", shape=note, style=filled, '
        'fillcolor="#9ECAE1", color="#009E73", penwidth=2, tooltip=pass];'
    )
    assert drawn['"s" -> "c"'] == '"s" -> "c" [color="#009E73"];'


def test_a_failed_element_is_vermillion_with_a_cross_and_blocks_what_it_supports(
    tmp_path: Path,
) -> None:
    (tmp_path / "e2.log").write_text("two", encoding="utf-8")

    drawn = _drawn(tmp_path, lambda: Fail("two tests failed"))

    assert drawn['"e1"'] == (
        f'"e1" [label={_marked("✘", "e1")}, id="e1", shape=note, style=filled, '
        'fillcolor="#D55E00", fontcolor=white, penwidth=2, '
        'tooltip="fail: two tests failed"];'
    )
    assert drawn['"s"'] == (
        f'"s" [label={_marked("◌", "s")}, id="s", shape=hexagon, style="filled,dashed", '
        'fillcolor="#EEEEEE", color="#999999", tooltip="skip: not run: e1 did not pass"];'
    )
    assert drawn['"s" -> "c"'] == '"s" -> "c" [color="#999999", style=dashed];'
    assert drawn['"c"'].endswith(
        'shape=rect, style="filled,rounded,dashed", fillcolor="#EEEEEE", color="#999999", '
        'tooltip="skip: not run: e1 did not pass"];'
    )


def test_a_support_from_a_failure_is_thicker(tmp_path: Path) -> None:
    @evidence("e1", observes={"log": "e1.txt"}, produces=["a"])
    def first(log: Path) -> Outcome:
        return Pass(a="a")

    @evidence("e2", observes={"log": "e1.txt"}, produces=["b"])
    def second(log: Path) -> Outcome:
        return Fail("no")

    @strategy("s", consumes=["a"])
    def gates(a: str) -> Outcome:
        return Pass()

    @conclusion("c", consumes=["b"])
    def ready(b: str) -> Outcome:
        return Pass()

    (tmp_path / "e1.txt").write_text("one", encoding="utf-8")
    steps = (first, second, gates, ready)
    registry = StepRegistry(s for s in map(step_of, steps) if s is not None)
    report = RunReport.of(run(RELEASE, registry, root=tmp_path), tmp_path)

    lines = [line.strip() for line in source(RELEASE, report).splitlines()]

    # No variable links e2 to s: the support is drawn, from a failure.
    assert '"e2" -> "s" [color="#D55E00", penwidth=2];' in lines


def _labelled_run(tmp_path: Path, label: str) -> tuple[Justification, RunReport]:
    """A model whose evidence ``e`` has ``label``, and the report of a run of it."""
    labelled = model(
        element("c", CONCLUSION), Element("e", label, EVIDENCE), relations=[("e", "c")]
    )

    @evidence("e", observes={"log": "e1.txt"}, produces=["a"])
    def checked(log: Path) -> Outcome:
        return Pass(a="a")

    @conclusion("c", consumes=["a"])
    def ready(a: str) -> Outcome:
        return Pass()

    (tmp_path / "e1.txt").write_text("one", encoding="utf-8")
    registry = StepRegistry(s for s in map(step_of, (checked, ready)) if s is not None)
    return labelled, RunReport.of(run(labelled, registry, root=tmp_path), tmp_path)


def test_a_status_label_is_wrapped_as_the_compiler_wraps_and_escaped_for_html(
    tmp_path: Path,
) -> None:
    label = 'The "release_candidate" passes every check & <gate> the team wrote, twice'
    labelled, report = _labelled_run(tmp_path, label)

    (node,) = [line for line in source(labelled, report).splitlines() if line.startswith('  "e" [')]

    plain = source(labelled).split('label="')[3].split('", id=')[0]
    assert plain.count("\\n") == 1  # the plain label breaks once: so does the marked one
    text = (
        "The &quot;release_candidate&quot; passes every<br/>"
        "check &amp; &lt;gate&gt; the team wrote, twice"
    )
    assert node.startswith(f'  "e" [label={_marked("✔", text)}, id="e", ')


def test_a_backslash_in_a_status_label_is_escaped(tmp_path: Path) -> None:
    labelled, report = _labelled_run(tmp_path, r"Reads \N in C:\temp")

    (node,) = [line for line in source(labelled, report).splitlines() if line.startswith('  "e" [')]

    assert _marked("✔", r"Reads \\N in C:\\temp") in node


@needs_dot
def test_a_backslash_in_a_status_label_is_drawn_as_written(tmp_path: Path) -> None:
    labelled, report = _labelled_run(tmp_path, r"Reads \N in C:\temp")

    svg = ElementTree.parse(write(tmp_path / "m.svg", labelled, report)).getroot()

    texts = {t.text for t in svg.iter("{http://www.w3.org/2000/svg}text")}
    assert r"Reads \N in C:\temp" in texts


def test_an_element_that_skips_on_its_own_account_has_a_thicker_border(tmp_path: Path) -> None:
    drawn = _drawn(tmp_path, lambda: Skip("not today"))

    assert drawn['"e1"'].startswith(f'"e1" [label={_marked("◌", "e1")}, ')
    assert drawn['"e1"'].endswith('color="#999999", tooltip="skip: not today", penwidth=2];')
    assert "penwidth" not in drawn['"s"']


def test_a_report_of_another_model_with_the_same_name_is_refused(tmp_path: Path) -> None:
    (tmp_path / "e1.txt").write_text("one", encoding="utf-8")
    report = RunReport.of(run(RELEASE, _steps(lambda: Pass(a="a"), lambda: Pass(b="b"))))
    rewired = model(
        element("c", CONCLUSION),
        element("s", STRATEGY),
        element("e1", EVIDENCE),
        element("e2", EVIDENCE),
        relations=[("s", "c"), ("e1", "s"), ("e2", "c")],
    )

    with pytest.raises(ValueError, match="what supports what"):
        source(rewired, report)


def test_a_report_of_another_justification_is_refused() -> None:
    other = RunReport("other", Verdict.PASS)

    with pytest.raises(ValueError, match="'other'"):
        source(RELEASE, other)


def _layout(dot_source: str) -> dict[str, tuple[str, ...]]:
    """Where ``dot`` puts each node, and how large it draws the graph, from ``-Tplain``."""
    plain = subprocess.run(
        [str(DOT), "-Tplain"], input=dot_source, capture_output=True, text=True, check=True
    ).stdout
    placed = {}
    for line in plain.splitlines():
        kind, *fields = line.split()
        if kind == "graph":
            placed["graph"] = tuple(fields[1:3])
        elif kind == "node":
            placed[fields[0]] = tuple(fields[1:5])
    return placed


_OUTCOMES = {
    "pass": (lambda: Pass(a="a"), lambda: Pass(b="b")),
    "fail": (lambda: Fail("no"), lambda: Fail("no")),
    "skip": (lambda: Skip("not here"), lambda: Skip("not here")),
}


@needs_dot
@pytest.mark.parametrize("e1", list(_OUTCOMES))
@pytest.mark.parametrize("e2", [*_OUTCOMES, "unreachable"])
def test_a_status_never_moves_the_diagram(tmp_path: Path, e1: str, e2: str) -> None:
    (tmp_path / "e1.txt").write_text("one", encoding="utf-8")
    if e2 != "unreachable":
        (tmp_path / "e2.log").write_text("two", encoding="utf-8")
    second = _OUTCOMES["pass" if e2 == "unreachable" else e2][1]
    registry = _steps(_OUTCOMES[e1][0], second)
    planned = RunReport.of(run(RELEASE, registry, root=tmp_path, dry_run=True), tmp_path)
    ran = RunReport.of(run(RELEASE, registry, root=tmp_path), tmp_path)
    assert {e.status for e in ran.elements} - {None}, "the run decided nothing"

    assert _layout(source(RELEASE, ran)) == _layout(source(RELEASE, planned))


# --- The dataflow ---------------------------------------------------------------------------


def test_the_diagram_adds_the_files_and_variables_the_steps_declare(tmp_path: Path) -> None:
    (tmp_path / "e2.log").write_text("two", encoding="utf-8")

    drawn = _drawn(tmp_path, lambda: Pass(a="a"))

    assert drawn['"artifact e1.txt"'] == (
        f'"artifact e1.txt" [label={_marked(None, "e1.txt", 14)}, fontname=Courier, '
        "fontsize=10, shape=folder];"
    )
    assert drawn['"variable a"'] == (
        f'"variable a" [label={_marked(None, "a", 14)}, fontname=Courier, fontsize=10, '
        "shape=ellipse];"
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


def test_a_file_that_could_not_be_reached_is_vermillion_with_a_warning(tmp_path: Path) -> None:
    drawn = _drawn(tmp_path, lambda: Pass(a="a"))  # no *.log

    assert drawn['"artifact *.log"'] == (
        f'"artifact *.log" [label={_marked("⚠", "*.log", 14)}, fontname=Courier, fontsize=10, '
        'shape=folder, color="#D55E00", penwidth=2];'
    )
    assert "color" not in drawn['"artifact e1.txt"']


def test_a_glob_is_not_unreachable_for_a_file_another_path_declares(tmp_path: Path) -> None:
    @evidence("e", observes={"logs": "*.log", "old": "old/b.log"}, produces=["a"])
    def reads(logs: list[Path], old: Path) -> Outcome:
        return Pass(a="a")

    @strategy("s", consumes=["a"])
    def judges(a: str) -> Outcome:
        return Pass()

    (tmp_path / "a.log").write_text("a", encoding="utf-8")  # old/b.log is missing
    small = model(element("s", STRATEGY), element("e", EVIDENCE), relations=[("e", "s")])
    registry = StepRegistry(s for s in map(step_of, (reads, judges)) if s is not None)
    report = RunReport.of(run(small, registry, root=tmp_path), tmp_path)

    drawn = source(small, report)

    (glob,) = [line for line in drawn.splitlines() if line.strip().startswith('"artifact *.log" [')]
    (file,) = [line for line in drawn.splitlines() if '"artifact old/b.log" [' in line]
    assert "color" not in glob
    assert 'color="#D55E00"' in file


def test_the_diagram_draws_what_is_observed_that_is_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("JPIPE_STAGE", raising=False)

    @evidence("e", observes={"stage": Env("JPIPE_STAGE")}, produces=["a"])
    def reads(stage: str) -> Outcome:
        return Pass(a=stage)

    @strategy("s", consumes=["a"])
    def judges(a: str) -> Outcome:
        return Pass()

    small = model(element("s", STRATEGY), element("e", EVIDENCE), relations=[("e", "s")])
    registry = StepRegistry(s for s in map(step_of, (reads, judges)) if s is not None)
    report = RunReport.of(run(small, registry, root=tmp_path), tmp_path)

    drawn = source(small, report)

    (node,) = [line for line in drawn.splitlines() if '"artifact env:JPIPE_STAGE" [' in line]
    assert 'color="#D55E00"' in node  # it is not set
    assert '"artifact env:JPIPE_STAGE" -> "e"' in drawn


def test_a_support_a_variable_already_links_is_not_drawn(tmp_path: Path) -> None:
    (tmp_path / "e2.log").write_text("two", encoding="utf-8")

    drawn = _drawn(tmp_path, lambda: Pass(a="a"))

    # e1 produces a and e2 produces b, which s consumes: the variables show the supports.
    assert '"e1" -> "s"' not in drawn
    assert '"e2" -> "s"' not in drawn
    assert drawn['"s" -> "c"'] == '"s" -> "c" [color="#009E73"];'


def test_a_support_no_variable_links_is_drawn(tmp_path: Path) -> None:
    @evidence("e1", observes={"log": "e1.txt"}, produces=["a"])
    def first(log: Path) -> Outcome:
        return Pass(a="a")

    @evidence("e2", observes={"log": "e1.txt"}, produces=["b"])
    def second(log: Path) -> Outcome:
        return Pass(b="b")

    @strategy("s", consumes=["a"])
    def gates(a: str) -> Outcome:
        return Pass()

    @conclusion("c", consumes=["b"])
    def ready(b: str) -> Outcome:
        return Pass()

    (tmp_path / "e1.txt").write_text("one", encoding="utf-8")
    steps = (first, second, gates, ready)
    registry = StepRegistry(s for s in map(step_of, steps) if s is not None)
    report = RunReport.of(run(RELEASE, registry, root=tmp_path), tmp_path)

    lines = [line.strip() for line in source(RELEASE, report).splitlines()]

    # b flows from e2 to c, which e2 does not support: the support of s is drawn.
    assert '"e1" -> "s" [color="#009E73"];' not in lines
    assert '"e2" -> "s" [color="#009E73"];' in lines
    assert (
        '"variable b" -> "c" [style=dashed, color="#0072B2", label=" consumes", fontsize=9];'
        in lines
    )


def test_a_variable_that_was_not_produced_is_dashed(tmp_path: Path) -> None:
    (tmp_path / "e2.log").write_text("two", encoding="utf-8")

    drawn = _drawn(tmp_path, lambda: Fail("no"))

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
    report = RunReport.of(run(RELEASE, registry))  # invalid: JP009, JP011, JP025
    lines = source(RELEASE, report).splitlines()

    for name in ("a", "unread", "missing"):
        (node,) = [line for line in lines if line.startswith(f'  "variable {name}" [')]
        assert node.startswith(f'  "variable {name}" [label={_marked("⚠", name, 14)}, ')
        assert node.endswith('color="#D55E00", penwidth=2];')


def test_a_value_its_consumer_does_not_resolve_to_is_vermillion() -> None:
    @strategy("s", consumes=["a"], produces=["a"])
    def loop(a: str) -> Outcome:
        return Pass(a=a)

    registry = StepRegistry(s for s in map(step_of, (loop,)) if s is not None)
    report = RunReport.of(run(RELEASE, registry))  # invalid: JP014, s does not support s
    lines = source(RELEASE, report).splitlines()

    (node,) = [line for line in lines if line.startswith('  "variable a" [')]
    assert node.startswith(f'  "variable a" [label={_marked("⚠", "a", 14)}, ')


# Two sub-arguments, a:e -> a:s -> a:c and b:e -> b:s -> b:c, both supporting s -> c.
BRANCHES = model(
    element("c", CONCLUSION),
    element("s", STRATEGY),
    element("a:c", SUB_CONCLUSION),
    element("a:s", STRATEGY),
    element("a:e", EVIDENCE),
    element("b:c", SUB_CONCLUSION),
    element("b:s", STRATEGY),
    element("b:e", EVIDENCE),
    relations=[
        ("s", "c"),
        ("a:c", "s"),
        ("a:s", "a:c"),
        ("a:e", "a:s"),
        ("b:c", "s"),
        ("b:s", "b:c"),
        ("b:e", "b:s"),
    ],
)


def _branches(tmp_path: Path, **consumes: str | Produced) -> list[str]:
    """The lines of the diagram of ``BRANCHES``, where a:e and b:e both produce ``x``, each
    consumed below its sub-conclusion, and s consumes ``consumes``."""
    (tmp_path / "log.txt").write_text("", encoding="utf-8")

    @evidence("a:e", observes={"log": "log.txt"}, produces=["x"])
    def first(log: Path) -> Outcome:
        return Pass(x=1)

    @strategy("a:s", consumes=["x"])
    def first_judged(x: int) -> Outcome:
        return Pass()

    @evidence("b:e", observes={"log": "log.txt"}, produces=["x"])
    def second(log: Path) -> Outcome:
        return Pass(x=2)

    @strategy("b:s", consumes=["x"])
    def second_judged(x: int) -> Outcome:
        return Pass()

    @strategy("s", consumes=consumes)
    def gates(**_: Any) -> Outcome:
        return Pass()

    steps = (first, first_judged, second, second_judged, gates)
    registry = StepRegistry(s for s in map(step_of, steps) if s is not None)
    report = RunReport.of(run(BRANCHES, registry, root=tmp_path), tmp_path)
    return [line.strip() for line in source(BRANCHES, report).splitlines()]


def _consumes(node: str, consumer: str) -> str:
    return (
        f'"{node}" -> "{consumer}" [style=dashed, color="#0072B2", label=" consumes", fontsize=9];'
    )


def test_two_producers_of_a_variable_are_two_values_each_with_its_consumers(
    tmp_path: Path,
) -> None:
    lines = _branches(tmp_path, a=Produced("x", by="a:c"), b=Produced("x", by="b:c"))

    for producer, consumer in (("a:e", "a:s"), ("b:e", "b:s")):
        (node,) = [line for line in lines if line.startswith(f'"variable x from {producer}" [')]
        assert node.startswith(f'"variable x from {producer}" [label={_marked(None, "x", 14)}, ')
        assert "D55E00" not in node
        assert _consumes(f"variable x from {producer}", consumer) in lines
        assert _consumes(f"variable x from {producer}", "s") in lines
    assert not [line for line in lines if line.startswith('"variable x" [')]
    assert _consumes("variable x from a:e", "b:s") not in lines


def test_a_variable_that_resolves_to_no_single_producer_is_a_vermillion_value(
    tmp_path: Path,
) -> None:
    lines = _branches(tmp_path, x="x")  # JP025: both sub-arguments produce x

    (node,) = [line for line in lines if line.startswith('"variable x" [')]
    assert node.startswith(f'"variable x" [label={_marked("⚠", "x", 14)}, ')
    assert _consumes("variable x", "s") in lines
    assert _consumes("variable x from a:e", "a:s") in lines


# --- Writing a diagram ----------------------------------------------------------------------


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


def test_a_diagram_that_cannot_be_drawn_leaves_the_previous_one_and_no_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = tmp_path / "m.png"
    previous.write_bytes(b"the previous drawing")

    def failing(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        Path(command[command.index("-o") + 1]).write_bytes(b"half a drawing")
        return subprocess.CompletedProcess(command, 1, "", "Error: syntax error\n")

    monkeypatch.setattr(subprocess, "run", failing)

    with pytest.raises(OSError, match="syntax error"):
        write(previous, RELEASE)

    assert previous.read_bytes() == b"the previous drawing"
    assert [p.name for p in tmp_path.iterdir()] == ["m.png"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_a_diagram_keeps_the_permissions_of_the_file_it_replaces(tmp_path: Path) -> None:
    drawn = tmp_path / "m.dot"
    drawn.write_text("the previous drawing", encoding="utf-8")
    drawn.chmod(0o640)

    write(drawn, RELEASE)

    assert stat.S_IMODE(drawn.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_a_new_diagram_has_the_permissions_a_new_file_gets(tmp_path: Path) -> None:
    umask = os.umask(0o022)
    try:
        write(tmp_path / "m.dot", RELEASE)
        assert stat.S_IMODE((tmp_path / "m.dot").stat().st_mode) == 0o644
    finally:
        os.umask(umask)


def test_a_link_to_a_diagram_is_written_through(tmp_path: Path) -> None:
    (tmp_path / "site").mkdir()
    target = tmp_path / "site" / "m.dot"
    target.write_text("the previous drawing", encoding="utf-8")
    link = tmp_path / "m.dot"
    link.symlink_to(target)

    assert write(link, RELEASE) == link

    assert link.is_symlink()
    assert target.read_text(encoding="utf-8") == source(RELEASE)
    assert [p.name for p in target.parent.iterdir()] == ["m.dot"]


def test_on_windows_a_diagram_a_reader_holds_open_is_replaced_once_it_is_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replace, held = os.replace, [2]

    def held_open(source: Any, destination: Any) -> None:
        if held[0]:
            held[0] -= 1
            raise PermissionError(13, "The process cannot access the file")
        replace(source, destination)

    monkeypatch.setattr(diagram, "_WINDOWS", True)
    monkeypatch.setattr(diagram.os, "replace", held_open)
    monkeypatch.setattr(diagram.time, "sleep", lambda _: None)

    write(tmp_path / "m.dot", RELEASE)

    assert (tmp_path / "m.dot").read_text(encoding="utf-8") == source(RELEASE)


def test_elsewhere_a_diagram_that_cannot_be_replaced_fails_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts: list[object] = []

    def refused(source: Any, destination: Any) -> None:
        attempts.append(destination)
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(diagram, "_WINDOWS", False)
    monkeypatch.setattr(diagram.os, "replace", refused)

    with pytest.raises(PermissionError):
        write(tmp_path / "m.dot", RELEASE)
    assert len(attempts) == 1
    assert list(tmp_path.iterdir()) == []


def test_a_diagram_is_written_whole_under_its_name(tmp_path: Path) -> None:
    drawn = tmp_path / "out" / "m.dot"
    drawn.parent.mkdir()
    drawn.write_text("the previous drawing", encoding="utf-8")

    write(drawn, RELEASE)

    assert drawn.read_text(encoding="utf-8") == source(RELEASE)
    assert [p.name for p in drawn.parent.iterdir()] == ["m.dot"]


@needs_dot
@pytest.mark.parametrize("fmt", [fmt for fmt in FORMATS if fmt != "dot"])
def test_every_format_is_rendered_by_graphviz(tmp_path: Path, fmt: str) -> None:
    written = write(tmp_path / "out" / f"m.{fmt}", RELEASE)

    assert written.stat().st_size > 0


@needs_dot
def test_an_svg_keeps_the_ids_and_the_statuses(tmp_path: Path) -> None:
    (tmp_path / "e1.txt").write_text("one", encoding="utf-8")
    report = RunReport.of(
        run(RELEASE, _steps(lambda: Fail("no"), lambda: Pass(b="b")), root=tmp_path), tmp_path
    )

    svg = ElementTree.parse(write(tmp_path / "m.svg", RELEASE, report)).getroot()

    namespace = {"svg": "http://www.w3.org/2000/svg"}
    groups = list(svg.iterfind(".//svg:g[@class='node']", namespace))
    titles = {g.findtext("svg:title", namespaces=namespace) for g in groups}
    assert titles == {
        "c",
        "s",
        "e1",
        "e2",
        "artifact e1.txt",
        "artifact *.log",
        "variable a",
        "variable b",
    }
    nodes = {g.get("id"): g for g in groups}
    assert {"c", "s", "e1", "e2"} <= set(nodes)
    fills = {
        node_id: {p.get("fill") for p in g.iterfind(".//svg:polygon", namespace)}
        for node_id, g in nodes.items()
    }
    assert "#d55e00" in {fill.lower() for fill in fills["e1"] if fill}


# --- Templates ------------------------------------------------------------------------------

# tests/unit/fixtures/multi_inheritance.{json,dot}: `jpipe process -i multi_inheritance.jd
# -m leaf_intermediate -f JSON` and `-f DOT` (jPipe 4.0.0), the .jd being the compiler's
# examples/006_multi_inheritance.jd: a justification under a chain of two templates.
FIXTURES = Path(__file__).parent / "fixtures"
TEMPLATED = Path(__file__).parents[1] / "e2e" / "scenarios" / "templated"


def test_a_template_chain_is_drawn_in_the_compilers_notation() -> None:
    chain = loader.load(FIXTURES / "multi_inheritance.json")

    assert source(chain) == (FIXTURES / "multi_inheritance.dot").read_text(encoding="utf-8")


def _templated_run() -> dict[str, str]:
    """The diagram's lines of a run of the templated scenario, by node or edge."""
    justification = loader.load(TEMPLATED / "justification.json")
    with imported([TEMPLATED / "steps.py"]) as modules:
        result = engine.run(justification, StepRegistry.from_modules(modules), root=TEMPLATED)
    lines = source(justification, RunReport.of(result, TEMPLATED)).splitlines()
    return {line.strip().partition(" [")[0].rstrip(";"): line.strip() for line in lines}


def test_a_template_support_is_drawn_from_its_placeholder_even_when_a_variable_links_it() -> None:
    drawn = _templated_run()

    tested, gates = '"readiness:quality:tested"', '"readiness:quality:gates"'
    assert f"{tested} -> {gates}" not in drawn
    assert drawn[f'"readiness:quality:tested@abstract" -> {gates}'].endswith('[color="#009E73"];')
    assert f'{tested} -> "variable tested"' in drawn
    assert f'"variable tested" -> {gates}' in drawn


def test_a_placeholder_has_no_status_and_the_element_filling_it_has_one() -> None:
    drawn = _templated_run()

    assert drawn['"readiness:quality:tested@abstract"'] == (
        '"readiness:quality:tested@abstract" [label="Testing is demonstrated", '
        'id="readiness:quality:tested@abstract", shape=rect, style=dotted];'
    )
    assert drawn['"readiness:quality:tested"'].endswith("penwidth=2, tooltip=pass];")
    assert drawn['"readiness:quality:tested" -> "readiness:quality:tested@abstract"'] == (
        '"readiness:quality:tested" -> "readiness:quality:tested@abstract" '
        "[arrowhead=empty, style=dotted];"
    )


def test_an_element_the_template_chain_does_not_place_is_drawn_outside_it() -> None:
    chain = TemplateChain(("e1",), (Template("t", ("c", "s")),))
    partial = Justification("m", RELEASE.elements, RELEASE.relations, chain)

    nodes = [
        line.split(" [")[0].strip() for line in source(partial).splitlines() if " [label" in line
    ]

    assert nodes == ['"e1"', '"e2"', '"c"', '"s"']


def test_a_template_name_is_wrapped_and_escaped_as_the_compiler_does() -> None:
    chain = TemplateChain(
        ("e1", "e2", "s"), (Template("a_long_template_name_for_wrapping", ("c",)),)
    )
    named = Justification("m", RELEASE.elements, RELEASE.relations, chain)

    assert '    label="<<template>>\\na\\_long\\_template\\_name\\_for\\_wrapping";' in (
        source(named).splitlines()
    )
