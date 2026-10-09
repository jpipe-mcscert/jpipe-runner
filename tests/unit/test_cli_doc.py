"""docs/cli.md documents every option and every exit code, and its examples run (#127, #146).

The page's options tables list exactly the options of ``cli.parser()``, and of the
``impact`` and ``status`` subcommands, and its exit codes table exactly ``cli.ExitCode``.
Each console session on the page is replayed in a copy of the release example, and must
print what the page shows.
"""

import argparse
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from jpipe_runner.cli import ExitCode, impact_parser, main, parser, status_parser
from tests.conftest import REPO_ROOT
from tests.console import blocks, replay
from tests.scenarios import GOLDEN_FILE, SCENARIOS_ROOT

PAGE = (REPO_ROOT / "docs" / "cli.md").read_text(encoding="utf-8")
SESSIONS = blocks(PAGE)


def _section(title: str) -> str:
    start = PAGE.index(f"\n## {title}\n")
    end = PAGE.find("\n## ", start + 1)
    return PAGE[start : end if end != -1 else len(PAGE)]


def _first_cells(section: str) -> Iterator[str]:
    """The first cell of each row of the tables in ``section``, without the header's."""
    for line in section.splitlines():
        if line.startswith("| ") and not line.startswith("|---"):
            yield line.split("|")[1].strip()


@pytest.mark.parametrize(
    ("section", "command", "positional"),
    [
        ("Options", parser, "JUSTIFICATION"),
        ("Impact analysis", impact_parser, "JUSTIFICATION"),
        ("Staleness", status_parser, "REPORT"),
    ],
)
def test_each_options_table_lists_every_option_of_its_command(
    section: str, command: Callable[[], argparse.ArgumentParser], positional: str
) -> None:
    documented = {
        name.strip().strip("`").split()[0]
        for cell in _first_cells(_section(section))
        for name in cell.split(",")
        if cell.startswith("`")
    }
    options = {option for action in command()._actions for option in action.option_strings}

    assert documented == options | {positional}


def test_the_exit_codes_table_lists_every_exit_code() -> None:
    documented = {cell for cell in _first_cells(_section("Exit codes")) if cell.isdigit()}

    assert documented == {str(int(code)) for code in ExitCode}


def test_the_page_has_its_sessions() -> None:
    assert len(SESSIONS) == 6


def _changed_since_a_run(capsys: pytest.CaptureFixture[str]) -> None:
    """The release example after a run that wrote its report, with its changelog edited."""
    assert main(["--library", "steps.py", "--report", "report.json", "justification.json"]) == 0
    capsys.readouterr()
    Path("mock/CHANGELOG.md").write_text("2.1\n", encoding="utf-8")


# What a session needs done before it, by its first command.
SETUP = {"jpipe-runner status report.json": _changed_since_a_run}


@pytest.mark.parametrize("session", SESSIONS, ids=lambda session: session.splitlines()[0])
def test_every_session_prints_what_the_page_shows(
    session: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workdir = tmp_path / "release_example"
    shutil.copytree(
        SCENARIOS_ROOT / "release_example",
        workdir,
        ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
    )
    monkeypatch.chdir(workdir)
    monkeypatch.setenv("COLUMNS", "80")  # the width argparse lays its usage out to
    monkeypatch.delenv("NO_COLOR", raising=False)
    first = session.splitlines()[0].removeprefix("$ ")
    SETUP.get(first, lambda _: None)(capsys)

    assert replay(session, capsys) == session
