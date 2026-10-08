"""docs/end-to-end.md quotes the release example's step library, its validation and its runs.

Every function of ``tests/e2e/scenarios/release_example/steps.py`` appears in the page,
character for character, and so does what validation reports on the release and composed
examples, and what running them does, so the walkthrough cannot drift from the code the
e2e suite runs.
"""

import ast
import shutil
import types
from collections.abc import Callable
from pathlib import Path

import pytest

from jpipe_runner import loader
from jpipe_runner.diagnostics import Diagnostic
from jpipe_runner.engine import RunResult, run
from jpipe_runner.rules import RULES
from jpipe_runner.steps import StepRegistry
from jpipe_runner.validation import ValidationContext, ValidationReport
from tests.conftest import REPO_ROOT

PAGE = (REPO_ROOT / "docs" / "end-to-end.md").read_text(encoding="utf-8")
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
    """A run as the page shows it: each element in the order run, then the verdict."""
    width = max(len(r.element.id) for r in result)
    lines = []
    for r in result:
        name = r.binding.step.name if r.binding else "(no function)"
        lines.append(f"{r.status:<4}  {r.element.id:<{width}}  {name}")
        for o in r.observed:
            seen = (
                f"sha256 {(o.sha256 or '')[:12]}…, {o.size} bytes" if o.reachable else "unreachable"
            )
            lines.append(f"      observed {o.path} ({seen})")
        if r.reason:
            lines.append(f"      {r.reason}")
    lines.append(f"verdict: {result.verdict}")
    return "```\n" + "\n".join(lines) + "\n```"


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
    assert _as_shown(result.diagnostics) in PAGE


def test_the_page_quotes_the_run_of_the_refined_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    libraries = ["draft_steps.py", "tested_steps.py"]
    result = _run("composed", libraries, tmp_path, monkeypatch)
    assert result.verdict == "pass"
    assert _as_run(result) in PAGE
