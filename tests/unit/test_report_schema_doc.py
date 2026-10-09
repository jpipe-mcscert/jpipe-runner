"""docs/report-schema.md documents the JSON report as the code writes it (#122, #145).

Every example on the page is a whole report, recomputed by running its scenario, and
matches the schema; and every field the schema defines is documented on the page.
"""

import json
import re
import shutil
import types
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from jpipe_runner import loader
from jpipe_runner.engine import run
from jpipe_runner.json_report import SCHEMA, document
from jpipe_runner.model import InvalidJustificationError
from jpipe_runner.report import RunReport
from jpipe_runner.steps import StepRegistry
from tests.conftest import REPO_ROOT

PAGE = (REPO_ROOT / "docs" / "report-schema.md").read_text(encoding="utf-8")
EXAMPLES = [json.loads(block) for block in re.findall(r"^```json\n(.*?)^```", PAGE, re.M | re.S)]
SCENARIOS = REPO_ROOT / "tests" / "e2e" / "scenarios"


def _run(name: str, workdir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the scenario ``name``, as the working directory of a run."""
    copy = workdir / name
    shutil.copytree(SCENARIOS / name, copy, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.chdir(copy)
    return copy


def _report(copy: Path) -> dict[str, Any]:
    module = types.ModuleType("steps")
    source = (copy / "steps.py").read_text(encoding="utf-8")
    exec(compile(source, str(copy / "steps.py"), "exec"), module.__dict__)
    justification = loader.load(copy / "justification.json")
    return document(RunReport.of(run(justification, StepRegistry.from_modules([module]))))


def test_the_page_has_its_three_examples() -> None:
    assert len(EXAMPLES) == 3


@pytest.mark.parametrize("example", EXAMPLES, ids=["failed", "raised", "refused"])
def test_every_example_matches_the_schema(example: dict[str, Any]) -> None:
    Draft202012Validator(SCHEMA).validate(example)


def test_the_page_shows_the_report_of_a_failing_test_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy = _run("release_example", tmp_path, monkeypatch)
    junit = copy / "mock" / "junit.xml"
    junit.write_text(
        junit.read_text(encoding="utf-8").replace('failures="0"', 'failures="2"'), encoding="utf-8"
    )

    assert _report(copy) == EXAMPLES[0]


def test_the_page_shows_the_report_of_a_step_that_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _report(_run("exception_handling", tmp_path, monkeypatch)) == EXAMPLES[1]


def test_the_page_shows_the_report_of_a_refused_model() -> None:
    with pytest.raises(InvalidJustificationError) as error:
        loader.load(SCENARIOS / "circular_dependency" / "justification.json")

    assert document(RunReport.refused(error.value)) == EXAMPLES[2]


def _fields(definition: dict[str, Any]) -> set[str]:
    return set(definition["properties"])


@pytest.mark.parametrize(
    "fields",
    [
        pytest.param(_fields(SCHEMA), id="report"),
        pytest.param(_fields(SCHEMA["$defs"]["element"]), id="element"),
        pytest.param(_fields(SCHEMA["$defs"]["artifact"]), id="artifact"),
        pytest.param(_fields(SCHEMA["$defs"]["diagnostic"]), id="diagnostic"),
        pytest.param(_fields(SCHEMA["$defs"]["traceback"]), id="traceback"),
        pytest.param(_fields(SCHEMA["$defs"]["summary"]), id="summary"),
    ],
)
def test_every_field_of_the_schema_is_documented(fields: set[str]) -> None:
    first_cells = re.findall(r"^\| ([^|]+) \|", PAGE, re.M)
    documented = {name for cell in first_cells for name in re.findall(r"`([a-z_0-9]+)`", cell)}
    assert fields <= documented
