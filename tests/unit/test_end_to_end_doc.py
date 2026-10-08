"""docs/end-to-end.md quotes the release example's step library, and its validation, as they are.

Every function of ``tests/e2e/scenarios/release_example/steps.py`` appears in the page,
character for character, and so does what validation reports on the release and composed
examples, so the walkthrough cannot drift from the code the e2e suite runs.
"""

import ast
import types
from collections.abc import Callable
from pathlib import Path

import pytest

from jpipe_runner import loader
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


def _as_shown(report: ValidationReport) -> str:
    """The diagnostics as the page shows them: each one, then its fix."""
    lines = []
    for diagnostic in report.diagnostics:
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
    assert _as_shown(report) in PAGE


def test_the_page_quotes_validation_of_the_refined_model() -> None:
    report = _validate(
        "composed",
        _module(SCENARIOS / "composed" / "draft_steps.py", "draft_steps"),
        _module(SCENARIOS / "composed" / "tested_steps.py", "tested_steps"),
    )
    assert report.passed
    assert _as_shown(report) in PAGE
