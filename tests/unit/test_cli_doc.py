"""docs/cli.md documents every option and every exit code, and its examples run (#127).

The page's options table lists exactly the options of ``cli.parser()``, and its exit codes
table exactly ``cli.ExitCode``. Each console session on the page is replayed in a copy of
the release example, and must print what the page shows.
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from jpipe_runner.cli import ExitCode, parser
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


def test_the_options_table_lists_every_option_of_the_command() -> None:
    documented = {
        name.strip().strip("`").split()[0]
        for cell in _first_cells(_section("Options"))
        for name in cell.split(",")
    } - {"Option"}
    options = {option for action in parser()._actions for option in action.option_strings}

    assert documented == options | {"JUSTIFICATION"}


def test_the_exit_codes_table_lists_every_exit_code() -> None:
    documented = {cell for cell in _first_cells(_section("Exit codes")) if cell.isdigit()}

    assert documented == {str(int(code)) for code in ExitCode}


def test_the_page_has_its_sessions() -> None:
    assert len(SESSIONS) == 4


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

    assert replay(session, capsys) == session
