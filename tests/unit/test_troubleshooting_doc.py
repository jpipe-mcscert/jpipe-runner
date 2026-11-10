"""docs/troubleshooting.md shows each problem as the command reports it (#129).

Each console session on the page is replayed in a copy of the release example, after the
setup that makes the problem it describes, and must print what the page shows.
"""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from jpipe_runner import cli
from jpipe_runner.cli import main
from tests.conftest import REPO_ROOT
from tests.console import blocks, replay
from tests.scenarios import GOLDEN_FILE, SCENARIOS_ROOT

PAGE = (REPO_ROOT / "docs" / "troubleshooting.md").read_text(encoding="utf-8")
SESSIONS = blocks(PAGE)

Setup = Callable[[Path, pytest.MonkeyPatch, pytest.CaptureFixture[str]], None]


def _no_graphviz(workdir: Path, monkeypatch: pytest.MonkeyPatch, _: object) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)


def _imports_a_module_of_its_own(workdir: Path, *_: object) -> None:
    (workdir / "checks").mkdir()
    (workdir / "checks" / "release_checks.py").write_text("RELEASE = '2.0'\n", encoding="utf-8")
    steps = workdir / "steps.py"
    source = steps.read_text(encoding="utf-8")
    old = 'RELEASE = "2.0"\n'
    assert source.count(old) == 1
    steps.write_text(source.replace(old, "from release_checks import RELEASE\n"), "utf-8")


def _from_the_parent(workdir: Path, monkeypatch: pytest.MonkeyPatch, _: object) -> None:
    monkeypatch.chdir(workdir.parent)


def _after_a_dry_run(
    workdir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--library", "steps.py", "--dry-run", "--report", "report.json", "justification.json"]
    assert main(argv) == 0
    capsys.readouterr()


# What a session needs done before it, by its first command.
SETUP: dict[str, Setup] = {
    "jpipe-runner --library steps.py --diagram release.svg justification.json": _no_graphviz,
    "jpipe-runner --library steps.py justification.json": _imports_a_module_of_its_own,
    "jpipe-runner --library release/steps.py release/justification.json": _from_the_parent,
    "jpipe-runner status report.json": _after_a_dry_run,
}


def test_the_page_has_its_sessions() -> None:
    assert len(SESSIONS) == 6


def test_every_setup_is_for_a_session_on_the_page() -> None:
    firsts = {session.splitlines()[0].removeprefix("$ ") for session in SESSIONS}

    assert set(SETUP) <= firsts


@pytest.mark.parametrize("session", SESSIONS, ids=lambda session: session.splitlines()[0])
def test_every_session_prints_what_the_page_shows(
    session: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workdir = tmp_path / "release"
    shutil.copytree(
        SCENARIOS_ROOT / "release_example",
        workdir,
        ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
    )
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("COLUMNS", "80")  # the width argparse lays its usage out to
    monkeypatch.delenv("NO_COLOR", raising=False)
    first = session.splitlines()[0].removeprefix("$ ")
    SETUP.get(first, lambda *_: None)(workdir, monkeypatch, capsys)

    assert replay(session, capsys) == session
