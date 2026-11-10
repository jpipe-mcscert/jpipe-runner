"""README.md shows the release example as it is, and its run as it prints (#129).

The step library of its 60-second example is the release example's, character for
character after its docstring, and its console session is replayed in a copy of it.
"""

import ast
import shutil
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT
from tests.console import blocks, replay
from tests.scenarios import GOLDEN_FILE, SCENARIOS_ROOT

PAGE = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
RELEASE = SCENARIOS_ROOT / "release_example"


def test_the_library_is_the_release_example_s() -> None:
    source = (RELEASE / "steps.py").read_text(encoding="utf-8")
    docstring = ast.parse(source).body[0]
    assert isinstance(docstring, ast.Expr)
    after = "".join(source.splitlines(keepends=True)[docstring.end_lineno :]).lstrip("\n")

    assert blocks(PAGE, "python") == [after]


def test_the_session_prints_what_the_page_shows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (session,) = blocks(PAGE)
    workdir = tmp_path / "release"
    shutil.copytree(RELEASE, workdir, ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"))
    monkeypatch.chdir(workdir)
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert replay(session, capsys) == session
