"""The examples of docs/authoring.md run as written, and the output it quotes is real.

Every ``python`` block of the page is executed, in order, in one namespace, so a later
example may use what an earlier one declared. A block that stops working with the API it
documents fails here. The diagnostics the page quotes are recomputed, by running the
examples' steps, or by validating the libraries of the composed scenarios it describes.
"""

import ast
import json
import re
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from jpipe_runner import libraries, loader
from jpipe_runner.diagnostics import Diagnostic
from jpipe_runner.engine import Status, run
from jpipe_runner.rules import RULES
from jpipe_runner.steps import StepRegistry, step_of
from jpipe_runner.validation import ValidationContext
from tests.conftest import REPO_ROOT

PAGE = (REPO_ROOT / "docs" / "authoring.md").read_text(encoding="utf-8")
BLOCKS = re.findall(r"^```python\n(.*?)^```", PAGE, re.MULTILINE | re.DOTALL)

# The module name the page shows for its examples' steps.
MODULE = "steps"

SCENARIOS = REPO_ROOT / "tests" / "e2e" / "scenarios"


def _examples() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": MODULE}
    for block in BLOCKS:
        exec(compile(block, "docs/authoring.md", "exec"), namespace)
    return namespace


def test_the_page_has_examples() -> None:
    assert len(BLOCKS) >= 5


def test_every_example_runs() -> None:
    assert _examples()


def test_the_page_quotes_what_a_pass_without_a_declared_value_reports(tmp_path: Path) -> None:
    examples = _examples()
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "junit.xml").write_text(
        '<testsuite tests="3" failures="0"/>', encoding="utf-8"
    )
    model = {
        "name": "release",
        "type": "justification",
        "elements": [
            {"id": "release:c", "type": "conclusion", "label": "Ready"},
            {"id": "release:s", "type": "strategy", "label": "Every test passed"},
            {"id": "release:e1", "type": "evidence", "label": "The test suite ran"},
        ],
        "relations": [
            {"source": "release:s", "target": "release:c"},
            {"source": "release:e1", "target": "release:s"},
        ],
    }
    functions = (examples["the_test_suite_ran"], examples["every_test_passed"])
    registry = StepRegistry(step for step in map(step_of, functions) if step is not None)

    result = run(loader.loads(json.dumps(model)), registry, root=tmp_path)

    assert result.result("release:s").status is Status.SKIP
    (diagnostic,) = result.diagnostics
    assert _quoted(diagnostic) in PAGE


def _quoted(diagnostic: Diagnostic) -> str:
    """A diagnostic as the page quotes it: itself, then its fix."""
    return f"```\n{diagnostic}\n  fix: {diagnostic.fix}\n```"


def _library(path: Path, edit: Callable[[str], str] = str) -> types.ModuleType:
    """The library at ``path``, after ``edit``, as a module named after its file."""
    module = types.ModuleType(path.stem)
    exec(compile(edit(path.read_text(encoding="utf-8")), str(path), "exec"), module.__dict__)
    return module


def _validated(scenario: str, *modules: types.ModuleType) -> tuple[Diagnostic, ...]:
    justification = loader.load(SCENARIOS / scenario / "justification.json")
    registry = StepRegistry.from_modules(modules)
    return RULES.run(ValidationContext.of(justification, registry)).diagnostics


def test_the_page_quotes_two_libraries_with_one_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    for model in ("tested", "documented"):
        (tmp_path / model).mkdir()
        (tmp_path / model / "steps.py").write_text("", encoding="utf-8")
    with (
        pytest.raises(libraries.LibraryLoadError) as error,
        libraries.imported(["tested/steps.py", "documented/steps.py"]),
    ):
        pass
    (diagnostic,) = error.value.diagnostics
    assert _quoted(diagnostic) in PAGE


def test_the_page_quotes_an_assembled_model_without_its_strategy() -> None:
    assembled = SCENARIOS / "assembled"
    sources = (assembled / "tested_steps.py", assembled / "documented_steps.py")
    (diagnostic,) = _validated("assembled", *map(_library, sources))
    assert diagnostic.code == "JP005"
    assert _quoted(diagnostic) in PAGE


def test_the_page_quotes_the_step_of_the_assembled_strategy() -> None:
    source = (SCENARIOS / "assembled" / "readiness_steps.py").read_text(encoding="utf-8")
    (function,) = [node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)]
    first = min(decorator.lineno for decorator in function.decorator_list)
    assert "\n".join(source.splitlines()[first - 1 : function.end_lineno]) in PAGE


def _without_the_hooks_step(source: str) -> str:
    start = source.index('@evidence("draft:tests"')
    return source[:start] + source[source.index('@evidence("draft:changelog"') :]


def test_the_page_quotes_a_refined_model_without_the_hooks_step() -> None:
    composed = SCENARIOS / "composed"
    draft = _library(composed / "draft_steps.py", _without_the_hooks_step)
    (diagnostic,) = _validated("composed", draft, _library(composed / "tested_steps.py"))
    assert diagnostic.code == "JP009"
    assert _quoted(diagnostic) in PAGE


def test_the_page_quotes_a_strategy_ignoring_what_a_merged_element_produces() -> None:
    unified = SCENARIOS / "unified"
    names = ("checked_steps.py", "argued_steps.py", "release_steps.py")
    found = _validated("unified", *(_library(unified / name) for name in names))
    (diagnostic,) = [d for d in found if d.code == "JP013"]
    assert _quoted(diagnostic) in PAGE
