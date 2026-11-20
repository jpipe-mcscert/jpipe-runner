"""docs/events.md documents the events of a run as the code writes them (#169).

Its console session is replayed in a copy of the release example whose test report records
two failures, and the events the page quotes are those the run wrote, but for
``elapsed_ms``, which differs from run to run. Every field of every event is documented on
the page, in the table of its event.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from jpipe_runner import events
from tests.conftest import REPO_ROOT
from tests.console import blocks, replay
from tests.scenarios import GOLDEN_FILE, SCENARIOS_ROOT
from tests.streams import VALIDATOR, read

PAGE = (REPO_ROOT / "docs" / "events.md").read_text(encoding="utf-8")
COMMON = ("event", "seq", "elapsed_ms")


def _timeless(found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**event, "elapsed_ms": 0} for event in found]


@pytest.fixture
def failing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The release example, with a test report that records two failures."""
    copy = tmp_path / "release_example"
    shutil.copytree(
        SCENARIOS_ROOT / "release_example",
        copy,
        ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
    )
    junit = copy / "mock" / "junit.xml"
    junit.write_text(
        junit.read_text(encoding="utf-8").replace('failures="0"', 'failures="2"'),
        encoding="utf-8",
    )
    monkeypatch.chdir(copy)
    monkeypatch.delenv("NO_COLOR", raising=False)
    return copy


def test_the_page_quotes_the_run_and_the_events_it_wrote(
    failing: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (session,) = blocks(PAGE)
    (quoted,) = blocks(PAGE, "jsonl")

    assert replay(session, capsys) == session
    shown = [json.loads(line) for line in quoted.splitlines()]
    for event in shown:
        VALIDATOR.validate(event)
    assert _timeless(shown) == _timeless(read(failing / "run.jsonl"))


def _section(title: str) -> str:
    start = PAGE.index(f"\n{title}\n")
    end = PAGE.find("\n#", start + 1)
    return PAGE[start : end if end != -1 else len(PAGE)]


def _first_cells(section: str) -> list[str]:
    """The first cell of each row of the tables in ``section``, without the header's."""
    rows = [line for line in section.splitlines() if line.startswith("| ")]
    cells = [row.split("|")[1].strip() for row in rows if not row.startswith("|---")]
    return [re.sub(r"^`(.*)`$", r"\1", cell) for cell in cells if cell != "Field"]


def test_every_event_starts_with_the_common_fields() -> None:
    assert _first_cells(_section("## The events")) == list(COMMON)


@pytest.mark.parametrize("name", [ref["$ref"].split("/")[-1] for ref in events.SCHEMA["oneOf"]])
def test_each_event_documents_exactly_its_fields(name: str) -> None:
    properties = events.SCHEMA["$defs"][name]["properties"]
    assert properties["event"] == {"const": name}
    assert _first_cells(_section(f"### `{name}`")) == [
        field for field in properties if field not in COMMON
    ]
