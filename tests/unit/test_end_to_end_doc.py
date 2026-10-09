"""docs/end-to-end.md quotes the release example's step library, its validation and its runs.

Every function of ``tests/e2e/scenarios/release_example/steps.py`` appears in the page,
character for character, and so does what validation reports on the release and composed
examples, and what running them does, so the walkthrough cannot drift from the code the
e2e suite runs. Runs are quoted as their text report, and step 7 quotes the JSON report and
shows the diagrams of a run, which ``--update-goldens`` redraws where Graphviz is installed.
"""

import ast
import json
import re
import shutil
import types
from collections.abc import Callable
from pathlib import Path
from xml.etree import ElementTree

import pytest

from jpipe_runner import loader
from jpipe_runner.diagnostics import Diagnostic
from jpipe_runner.diagram import View, write
from jpipe_runner.engine import RunResult, run
from jpipe_runner.json_report import document
from jpipe_runner.report import RunReport
from jpipe_runner.rules import RULES
from jpipe_runner.steps import StepRegistry
from jpipe_runner.text_report import render
from jpipe_runner.validation import ValidationContext, ValidationReport
from tests.conftest import REPO_ROOT

PAGE = (REPO_ROOT / "docs" / "end-to-end.md").read_text(encoding="utf-8")
IMAGES = REPO_ROOT / "docs" / "images"
needs_dot = pytest.mark.skipif(
    shutil.which("dot") is None, reason="Graphviz's dot is not installed"
)
SCENARIOS = REPO_ROOT / "tests" / "e2e" / "scenarios"
LIBRARY = SCENARIOS / "release_example" / "steps.py"
SOURCE = LIBRARY.read_text(encoding="utf-8")
FUNCTIONS = [node for node in ast.parse(SOURCE).body if isinstance(node, ast.FunctionDef)]


def test_the_release_library_has_functions_to_quote() -> None:
    assert len(FUNCTIONS) == 3


@pytest.mark.parametrize("function", FUNCTIONS, ids=lambda function: function.name)
def test_the_page_quotes_each_function_verbatim(function: ast.FunctionDef) -> None:
    lines = SOURCE.splitlines()
    first = min(d.lineno for d in function.decorator_list)
    quoted = "\n".join(lines[first - 1 : function.end_lineno])
    assert quoted in PAGE


def _module(path: Path, name: str, edit: Callable[[str], str] = str) -> types.ModuleType:
    """The library at ``path``, imported as ``name``, the name the page shows for it."""
    module = types.ModuleType(name)
    exec(compile(edit(path.read_text(encoding="utf-8")), str(path), "exec"), module.__dict__)
    return module


def _validate(scenario: str, *modules: types.ModuleType) -> ValidationReport:
    justification = loader.load(SCENARIOS / scenario / "justification.json")
    return RULES.run(ValidationContext.of(justification, StepRegistry.from_modules(modules)))


def _as_shown(diagnostics: tuple[Diagnostic, ...]) -> str:
    """The diagnostics as the page shows them: each one, then its fix."""
    lines = []
    for diagnostic in diagnostics:
        lines.append(str(diagnostic))
        if diagnostic.fix:
            lines.append(f"  fix: {diagnostic.fix}")
    return "```\n" + "\n".join(lines) + "\n```"


def _misspelled(source: str) -> str:
    """The release library, with the strategy consuming ``tests_passed``."""
    typo = (
        source.replace(
            'consumes=["tests_pass", "changelog_ok"]', 'consumes=["tests_passed", "changelog_ok"]'
        )
        .replace("tests_pass: bool, changelog_ok", "tests_passed: bool, changelog_ok")
        .replace("if tests_pass and", "if tests_passed and")
    )
    assert typo.count("tests_passed") == 3
    return typo


def test_the_release_library_passes_validation() -> None:
    report = _validate("release_example", _module(LIBRARY, "steps"))
    assert report.diagnostics == ()
    assert "The release library passes every check: validation reports nothing." in PAGE


def test_the_page_quotes_validation_of_the_misspelled_library() -> None:
    report = _validate("release_example", _module(LIBRARY, "steps", _misspelled))
    assert 'consumes=["tests_passed", "changelog_ok"]' in PAGE
    assert _as_shown(report.diagnostics) in PAGE


def test_the_page_quotes_validation_of_the_refined_model() -> None:
    report = _validate(
        "composed",
        _module(SCENARIOS / "composed" / "draft_steps.py", "draft_steps"),
        _module(SCENARIOS / "composed" / "tested_steps.py", "tested_steps"),
    )
    assert report.passed
    assert _as_shown(report.diagnostics) in PAGE


def _as_run(result: RunResult) -> str:
    """A run as the page shows it: its text report, without colour."""
    return "```\n" + render(RunReport.of(result)) + "```"


def _run(
    scenario: str,
    libraries: list[str],
    workdir: Path,
    monkeypatch: pytest.MonkeyPatch,
    edit: Callable[[Path], object] = lambda _: None,
) -> RunResult:
    """Run a copy of ``scenario``, from its directory as the runner would, after ``edit``."""
    copy = workdir / scenario
    shutil.copytree(SCENARIOS / scenario, copy, ignore=shutil.ignore_patterns("__pycache__"))
    edit(copy)
    monkeypatch.chdir(copy)
    modules = [_module(copy / library, Path(library).stem) for library in libraries]
    return run(loader.load(copy / "justification.json"), StepRegistry.from_modules(modules))


def _two_failures(scenario: Path) -> None:
    report = scenario / "mock" / "junit.xml"
    text = report.read_text(encoding="utf-8")
    assert 'failures="0"' in text
    report.write_text(text.replace('failures="0"', 'failures="2"'), encoding="utf-8")


def test_the_page_quotes_the_run_of_the_release_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run("release_example", ["steps.py"], tmp_path, monkeypatch)
    assert result.diagnostics == ()
    assert _as_run(result) in PAGE


def test_the_page_quotes_the_run_of_a_failing_test_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run("release_example", ["steps.py"], tmp_path, monkeypatch, _two_failures)
    assert 'failures="2"' in PAGE
    assert _as_run(result) in PAGE


def test_the_page_quotes_the_run_without_a_test_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def remove_report(scenario: Path) -> None:
        (scenario / "mock" / "junit.xml").unlink()

    result = _run("release_example", ["steps.py"], tmp_path, monkeypatch, remove_report)
    assert _as_run(result) in PAGE
    assert result.validation.diagnostics == ()
    assert [d.code for d in result.diagnostics] == ["JP019"]


def test_the_page_quotes_the_run_of_the_refined_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    libraries = ["draft_steps.py", "tested_steps.py"]
    result = _run("composed", libraries, tmp_path, monkeypatch)
    assert result.verdict == "pass"
    assert _as_run(result) in PAGE


def test_the_page_quotes_the_json_report_of_the_failing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run("release_example", ["steps.py"], tmp_path, monkeypatch, _two_failures)
    step_7 = PAGE[PAGE.index("## 7. Reading the verdict") :]
    (quoted,) = re.findall(r"^```json\n(.*?)^```", step_7, re.MULTILINE | re.DOTALL)

    assert json.loads(quoted) == document(RunReport.of(result))["elements"][0]


SVG = "{http://www.w3.org/2000/svg}"
_SHAPES = {f"{SVG}polygon", f"{SVG}ellipse", f"{SVG}path"}


def _drawn(svg: Path) -> dict[str, tuple[set[str], set[str]]]:
    """Each node of ``svg``, by its DOT name: the fills and strokes of its shapes."""
    nodes = {}
    for group in ElementTree.parse(svg).getroot().iter(f"{SVG}g"):
        if group.get("class") == "node":
            title = group.findtext(f"{SVG}title") or ""
            shapes = [s for s in group.iter() if s.tag in _SHAPES]
            fills = {(s.get("fill") or "").lower() for s in shapes}
            strokes = {(s.get("stroke") or "").lower() for s in shapes}
            nodes[title] = (fills, strokes)
    return nodes


def test_the_page_shows_the_diagrams_of_the_failing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, update_goldens: bool
) -> None:
    result = _run("release_example", ["steps.py"], tmp_path, monkeypatch, _two_failures)
    pictures = {View.JUSTIFICATION: "release-fail.svg", View.DATAFLOW: "release-fail-dataflow.svg"}
    if update_goldens and shutil.which("dot"):
        for view, name in pictures.items():
            write(IMAGES / name, result.justification, RunReport.of(result), view=view)

    for name in pictures.values():
        assert f"(images/{name})" in PAGE
        drawn = _drawn(IMAGES / name)
        assert "#d55e00" in drawn["release:e1"][0], f"redraw {name} with --update-goldens"
        assert "#009e73" in drawn["release:e2"][1]
        assert {"#eeeeee"} <= drawn["release:s"][0] & drawn["release:c"][0]
    dataflow = _drawn(IMAGES / pictures[View.DATAFLOW])
    assert {"artifact mock/junit.xml", "artifact mock/CHANGELOG.md"} <= set(dataflow)
    assert "#999999" in dataflow["variable tests_pass"][1]
    assert "#999999" not in dataflow["variable changelog_ok"][1]


@needs_dot
def test_the_diagrams_on_the_page_are_rendered_from_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _run("release_example", ["steps.py"], tmp_path, monkeypatch, _two_failures)
    drawn = write(tmp_path / "drawn.svg", result.justification, RunReport.of(result))

    assert _drawn(drawn) == _drawn(IMAGES / "release-fail.svg")
