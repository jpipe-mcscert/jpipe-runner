"""docs/observables.md runs as written, on the ``observables`` scenario (ADR-0028).

The step library the page shows is the scenario's, verbatim. Every ``python`` block is
executed, in order, in one namespace. Each console session is replayed in a copy of the
scenario and must print what the page shows, and each JSON fragment is what the scenario's
report says of an element.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from jpipe_runner.cli import main
from tests.conftest import REPO_ROOT
from tests.console import blocks, replay
from tests.scenarios import GOLDEN_FILE, SCENARIOS_ROOT

PAGE = (REPO_ROOT / "docs" / "observables.md").read_text(encoding="utf-8")
SCENARIO = SCENARIOS_ROOT / "observables"
PYTHON = re.findall(r"^```python\n(.*?)^```", PAGE, re.MULTILINE | re.DOTALL)
SESSIONS = blocks(PAGE)
FRAGMENTS = [json.loads(block) for block in blocks(PAGE, "json")]

RUN = ["--library", "checks/steps.py", "--report", "report.json", "justification.json"]
# The element each JSON fragment of the page is about, in page order.
QUOTED = ["version", "environment"]


def test_the_page_has_its_examples() -> None:
    assert (len(PYTHON), len(SESSIONS), len(FRAGMENTS)) == (6, 3, len(QUOTED))


def test_the_page_shows_the_library_of_the_scenario() -> None:
    assert PYTHON[0] == (SCENARIO / "checks" / "steps.py").read_text(encoding="utf-8")


def test_every_example_runs() -> None:
    namespace: dict[str, Any] = {"__name__": "steps"}
    for block in PYTHON:
        exec(compile(block, "docs/observables.md", "exec"), namespace)


def test_the_page_draws_the_files_of_the_scenario() -> None:
    tree = PAGE.split("```\n", 2)[1]
    drawn = {line.strip() for line in tree.splitlines()}
    kept = (p for p in SCENARIO.rglob("*") if "__pycache__" not in p.parts)
    files = {p.name + "/" * p.is_dir() for p in kept} - {GOLDEN_FILE, "scenario.toml"}

    assert drawn == files


@pytest.mark.parametrize("session", SESSIONS, ids=lambda session: session.splitlines()[0])
def test_every_session_prints_what_the_page_shows(
    session: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workdir = tmp_path / "observables"
    shutil.copytree(SCENARIO, workdir, ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"))
    monkeypatch.chdir(workdir)
    monkeypatch.delenv("NO_COLOR", raising=False)
    if session.startswith("$ jpipe-runner status"):
        assert main(RUN) == 0  # the report it reads
        capsys.readouterr()

    assert replay(session, capsys) == session


@pytest.mark.parametrize(("element", "fragment"), list(zip(QUOTED, FRAGMENTS, strict=True)))
def test_each_fragment_is_what_the_report_says_of_its_element(
    element: str, fragment: dict[str, Any]
) -> None:
    report = json.loads((SCENARIO / GOLDEN_FILE).read_text(encoding="utf-8"))
    (reported,) = [e for e in report["elements"] if e["id"] == element]

    assert fragment == {key: reported[key] for key in fragment}
    assert list(fragment) == ["observes", "sources", "artifacts", "observations"]
