"""docs/tutorial.md shows the release example as it is, and its runs as they print (#125).

Every file the page asks the reader to save is the release example's, character for
character, so that a reader who copies them gets the runs the page shows. Each console
session is replayed in a copy of the scenario it runs on, after the edit the page asks
for.
"""

import ast
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT
from tests.console import blocks, replay
from tests.scenarios import GOLDEN_FILE, SCENARIOS_ROOT

PAGE = (REPO_ROOT / "docs" / "tutorial.md").read_text(encoding="utf-8")
RELEASE = SCENARIOS_ROOT / "release_example"
COMPOSED = SCENARIOS_ROOT / "composed"
SESSIONS = blocks(PAGE)


def _as_shown(path: Path) -> str:
    """The file's text as a fenced block holds it: with one final newline."""
    return path.read_text(encoding="utf-8").rstrip("\n") + "\n"


@pytest.mark.parametrize(
    ("path", "language"),
    [
        (RELEASE / "release.jd", "text"),
        (RELEASE / "justification.json", "json"),
        (RELEASE / "mock" / "junit.xml", "xml"),
        (RELEASE / "mock" / "CHANGELOG.md", "markdown"),
    ],
    ids=lambda value: value if isinstance(value, str) else value.name,
)
def test_the_page_shows_each_file_of_the_example_as_it_is(path: Path, language: str) -> None:
    assert _as_shown(path) in blocks(PAGE, language)


def test_the_page_shows_the_step_library_as_it_is_after_its_docstring() -> None:
    source = (RELEASE / "steps.py").read_text(encoding="utf-8")
    docstring = ast.parse(source).body[0]
    assert isinstance(docstring, ast.Expr)
    after = "".join(source.splitlines(keepends=True)[docstring.end_lineno :]).lstrip("\n")

    assert after in blocks(PAGE, "python")


def test_the_page_shows_the_refinement_of_the_composed_example() -> None:
    refinement = 'justification readiness is refine(draft, tested) {\n  hook: "tests"\n}\n'

    assert refinement in blocks(PAGE, "text")
    assert refinement in _as_shown(COMPOSED / "refine.jd")


def _two_failures(scenario: Path) -> None:
    report = scenario / "mock" / "junit.xml"
    text = report.read_text(encoding="utf-8")
    assert 'failures="0"' in text
    report.write_text(text.replace('failures="0"', 'failures="2"'), encoding="utf-8")


def _as_is(scenario: Path) -> None:
    """No edit."""


# The scenario each session runs on, in the order of the page, and the edit made first.
RUNS: list[tuple[str, Callable[[Path], None]]] = [
    ("release_example", _as_is),
    ("release_example", _two_failures),
    ("release_example", _as_is),
    ("composed", _as_is),
]


def test_the_page_has_a_session_per_run() -> None:
    assert len(SESSIONS) == len(RUNS)


@pytest.mark.parametrize(
    ("session", "run"),
    list(zip(SESSIONS, RUNS, strict=True)),
    ids=[f"{index}-{name}" for index, (name, _) in enumerate(RUNS, 1)],
)
def test_every_session_prints_what_the_page_shows(
    session: str,
    run: tuple[str, Callable[[Path], None]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    name, edit = run
    workdir = tmp_path / name
    shutil.copytree(
        SCENARIOS_ROOT / name,
        workdir,
        ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
    )
    edit(workdir)
    monkeypatch.chdir(workdir)
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert replay(session, capsys) == session
