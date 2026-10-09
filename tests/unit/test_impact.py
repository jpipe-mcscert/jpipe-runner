"""Impact and staleness, from a JSON report (#146, ADR-0025)."""

import hashlib
import json
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from jpipe_runner import impact, json_report
from jpipe_runner.engine import Verdict
from jpipe_runner.impact import (
    Change,
    ChangeKind,
    Impact,
    InvalidReportError,
    above,
    affected,
    changed_since,
    matches,
    read,
    render_impact,
    render_stale,
    stale,
)
from jpipe_runner.report import RunReport

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def _element(
    element_id: str,
    kind: str = "evidence",
    supports: Sequence[str] = (),
    observes: Sequence[str] = (),
    artifacts: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    return {
        "id": element_id,
        "label": f"The {element_id}",
        "kind": kind,
        "supports": list(supports),
        "observes": list(observes),
        "artifacts": list(artifacts),
    }


def _artifact(path: str, content: str | None) -> dict[str, Any]:
    """An artifact as a run recorded it: ``content`` is None if it was unreachable."""
    if content is None:
        return {"path": path, "reachable": False, "sha256": None, "size": None}
    data = content.encode()
    return {
        "path": path,
        "reachable": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


# e1 observes a file, e2 a glob; both support s, which supports c. e3 supports c alone.
RELEASE: dict[str, Any] = {
    "justification": "release",
    "elements": [
        _element("e1", supports=["s"], observes=["build/tests.log"]),
        _element("e2", supports=["s"], observes=["docs/**/*.md"]),
        _element("e3", supports=["c"], observes=["CHANGELOG.md"]),
        _element("s", "strategy", supports=["c"]),
        _element("c", "conclusion"),
    ],
}


# --- Matching ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("a.txt", "a.txt", True),
        ("a.txt", "b.txt", False),
        ("a.txt", "*.txt", True),
        ("d/a.txt", "*.txt", False),
        ("d/a.txt", "*/a.txt", True),
        ("d/a.txt", "d/?.txt", True),
        ("a.txt", "**/a.txt", True),
        ("d/e/a.txt", "**/a.txt", True),
        ("d/a.txt", "d/**/*.txt", True),
        ("d/e/f/a.txt", "d/**/*.txt", True),
        ("e/a.txt", "d/**/*.txt", False),
        ("b.txt", "[ab].txt", True),
        ("c.txt", "[ab].txt", False),
        ("a.TXT", "*.txt", False),
        (".hidden", "*", True),
        ("d/a.txt", "./d/a.txt", True),
        ("d/e/a.txt", "d/**", True),  # a trailing ** reaches everything below
    ],
)
def test_a_path_matches_as_path_glob_matches_it(path: str, pattern: str, expected: bool) -> None:
    assert matches(path, pattern) is expected


_SEGMENTS = st.sampled_from(["a", "b", ".c", "a.txt", "b.md"])
_PATTERN_SEGMENTS = st.sampled_from(["*", "**", "a", "a.txt", "*.txt", "?", "[ab]", ".*"])


@settings(deadline=None)
@given(
    files=st.lists(st.lists(_SEGMENTS, min_size=1, max_size=3), min_size=1, max_size=6),
    pattern=st.lists(_PATTERN_SEGMENTS, min_size=1, max_size=3),
)
def test_matches_agrees_with_path_glob(files: list[list[str]], pattern: list[str]) -> None:
    # Python 3.11's Path.glob takes a trailing ** for directories only, where 3.13 adds the
    # files: matches() takes the files, which only ever reports more.
    assume(pattern[-1] != "**")
    paths = {"/".join(parts) for parts in files}
    # A path cannot be both a file and a directory.
    assume(not any(other.startswith(f"{path}/") for path in paths for other in paths))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for path in paths:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text("x", encoding="utf-8")
        globbed = {
            found.relative_to(root).as_posix()
            for found in root.glob("/".join(pattern))
            if found.is_file()
        }

    assert {path for path in paths if matches(path, "/".join(pattern))} == globbed


# --- Impact --------------------------------------------------------------------------------


def test_above_is_every_element_supported_in_report_order() -> None:
    assert above(RELEASE, ["e1"]) == ("e1", "s", "c")
    assert above(RELEASE, ["e3", "e2"]) == ("e2", "e3", "s", "c")
    assert above(RELEASE, []) == ()


def test_a_changed_file_reaches_the_evidence_observing_it_and_what_it_supports() -> None:
    found = affected(RELEASE, ["docs/api/index.md", "README.md", "docs/api/index.md"])

    assert found == Impact(
        changed=("README.md", "docs/api/index.md"),
        evidence=("e2",),
        affected=("e2", "s", "c"),
        unobserved=("README.md",),
    )


def test_a_change_no_evidence_observes_affects_nothing() -> None:
    assert affected(RELEASE, ["README.md"]).affected == ()


def test_the_impact_is_rendered_for_people() -> None:
    text = render_impact(RELEASE, affected(RELEASE, ["build/tests.log", "README.md"]))

    assert text == (
        "Justification: release\n"
        "\n"
        "Changed files, and the evidence that observes them:\n"
        "  README.md        (no evidence)\n"
        "  build/tests.log  e1\n"
        "\n"
        "Affected (3 elements):\n"
        "  Evidence    The e1  # e1\n"
        "  Strategy    The s   # s\n"
        "  Conclusion  The c   # c\n"
    )


def test_no_change_is_rendered_as_such() -> None:
    assert render_impact(RELEASE, affected(RELEASE, [])).endswith(
        "No file changed: nothing is affected.\n"
    )


def test_changes_that_reach_nothing_are_rendered_as_such() -> None:
    assert render_impact(RELEASE, affected(RELEASE, ["README.md"])).endswith(
        "Nothing is affected: no evidence observes these files.\n"
    )


# --- Staleness -----------------------------------------------------------------------------


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "tests.log").write_text("ok", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.md").write_text("A", encoding="utf-8")
    return tmp_path


def _recorded(*elements: dict[str, Any]) -> dict[str, Any]:
    return {"justification": "release", "elements": list(elements)}


def test_nothing_is_stale_when_every_file_is_as_recorded(root: Path) -> None:
    document = _recorded(
        _element(
            "e1", observes=["build/tests.log"], artifacts=[_artifact("build/tests.log", "ok")]
        ),
        _element("e2", observes=["docs/*.md"], artifacts=[_artifact("docs/a.md", "A")]),
    )

    assert stale(document, root) == ()


@pytest.mark.parametrize(
    ("artifact", "kind"),
    [
        pytest.param(_artifact("build/tests.log", "was ok"), ChangeKind.CHANGED, id="changed"),
        pytest.param(_artifact("build/gone.log", "ok"), ChangeKind.VANISHED, id="vanished"),
        pytest.param(_artifact("build/tests.log", None), ChangeKind.APPEARED, id="appeared"),
    ],
)
def test_a_recorded_file_that_differs_now_is_stale(
    artifact: dict[str, Any], kind: ChangeKind, root: Path
) -> None:
    document = _recorded(_element("e1", observes=[artifact["path"]], artifacts=[artifact]))

    assert stale(document, root) == (Change("e1", artifact["path"], kind),)


def test_a_file_a_glob_matches_now_and_the_run_did_not_see_is_added(root: Path) -> None:
    (root / "docs" / "b.md").write_text("B", encoding="utf-8")
    document = _recorded(
        _element("e2", observes=["docs/*.md"], artifacts=[_artifact("docs/a.md", "A")])
    )

    assert stale(document, root) == (Change("e2", "docs/b.md", ChangeKind.ADDED),)


def test_a_glob_that_matched_nothing_finds_what_it_matches_now(root: Path) -> None:
    document = _recorded(
        _element("e2", observes=["docs/*.md"], artifacts=[_artifact("docs/*.md", None)])
    )

    assert stale(document, root) == (Change("e2", "docs/a.md", ChangeKind.ADDED),)


def test_evidence_that_observed_nothing_is_not_compared(root: Path) -> None:
    document = _recorded(_element("e2", observes=["docs/*.md"]))

    assert stale(document, root) == ()


def test_a_file_that_cannot_be_read_any_more_has_vanished(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(file: Path) -> tuple[str, int]:
        raise PermissionError(f"{file}: permission denied")

    monkeypatch.setattr(impact, "digest", unreadable)
    document = _recorded(
        _element("e1", observes=["build/tests.log"], artifacts=[_artifact("build/tests.log", "ok")])
    )

    assert stale(document, root) == (Change("e1", "build/tests.log", ChangeKind.VANISHED),)


def test_staleness_is_rendered_for_people() -> None:
    changes = [Change("e1", "build/tests.log", ChangeKind.CHANGED)]

    assert render_stale(RELEASE, changes) == (
        "Justification: release\n"
        "\n"
        "Changed since the run:\n"
        "  changed  build/tests.log  e1\n"
        "\n"
        "Stale (3 elements):\n"
        "  Evidence    The e1  # e1\n"
        "  Strategy    The s   # s\n"
        "  Conclusion  The c   # c\n"
    )


def test_freshness_is_rendered_as_such() -> None:
    assert render_stale(RELEASE, []).endswith("its report still holds.\n")


# --- Reading a report ----------------------------------------------------------------------


def test_a_report_is_read_back(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(json_report.dumps(RunReport("m", Verdict.PASS)), encoding="utf-8")

    assert read(path)["verdict"] == "pass"


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("not json", id="not JSON"),
        pytest.param("[]", id="not an object"),
        pytest.param('{"schema_version": "2.0"}', id="another major version"),
        pytest.param('{"schema_version": "1.0"}', id="not a report"),
    ],
)
def test_a_file_that_is_not_a_report_is_refused(text: str, tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(InvalidReportError):
        read(path)


def test_a_file_that_is_not_utf8_is_not_a_report(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_bytes(b"\xff\xfe{")

    with pytest.raises(InvalidReportError):
        read(path)


def test_a_report_that_cannot_be_read_is_an_os_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read(tmp_path / "missing.json")


def test_a_report_of_a_later_minor_version_is_read_and_its_new_fields_ignored(
    tmp_path: Path,
) -> None:
    document = json.loads(json_report.dumps(RunReport("m", Verdict.PASS)))
    document |= {"schema_version": "1.1", "duration": 3.5}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    assert read(path)["justification"] == "m"


def test_a_report_of_this_version_with_a_field_it_does_not_define_is_refused(
    tmp_path: Path,
) -> None:
    document = json.loads(json_report.dumps(RunReport("m", Verdict.PASS)))
    path = tmp_path / "report.json"
    path.write_text(json.dumps(document | {"duration": 3.5}), encoding="utf-8")

    with pytest.raises(InvalidReportError):
        read(path)


def test_the_stale_files_of_a_later_minor_version_are_found(root: Path) -> None:
    artifact = _artifact("build/tests.log", "was ok") | {"modified": "2026-10-09"}
    element = _element("e1", observes=["build/tests.log"], artifacts=[artifact])
    document = {"schema_version": "1.1", "justification": "release", "elements": [element]}

    assert stale(document, root) == (Change("e1", "build/tests.log", ChangeKind.CHANGED),)


# --- Changes since a revision --------------------------------------------------------------


def _git(root: Path, *arguments: str) -> None:
    identity = ["-c", "user.name=jpipe", "-c", "user.email=jpipe@example.org"]
    subprocess.run(["git", *identity, *arguments], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (tmp_path / "kept.txt").write_text("1", encoding="utf-8")
    (tmp_path / "edited.txt").write_text("1", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.txt").write_text("1", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "first")
    (tmp_path / "edited.txt").write_text("2", encoding="utf-8")
    (tmp_path / "sub" / "deep.txt").write_text("2", encoding="utf-8")
    (tmp_path / "new.txt").write_text("1", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("1", encoding="utf-8")
    return tmp_path


@needs_git
def test_changes_since_a_revision_are_the_edited_and_untracked_files(repository: Path) -> None:
    assert changed_since("HEAD", repository) == ["edited.txt", "new.txt", "sub/deep.txt"]


@needs_git
def test_a_changed_path_that_is_not_ascii_is_listed_as_it_is(repository: Path) -> None:
    (repository / "délai.txt").write_text("1", encoding="utf-8")

    assert "délai.txt" in changed_since("HEAD", repository)


@needs_git
def test_changes_since_a_revision_are_relative_to_the_root(repository: Path) -> None:
    assert changed_since("HEAD", repository / "sub") == ["deep.txt"]


@needs_git
def test_an_unknown_revision_is_an_os_error(repository: Path) -> None:
    with pytest.raises(OSError, match="git diff failed"):
        changed_since("no-such-revision", repository)


def test_an_option_is_not_a_revision(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a git revision"):
        changed_since("--output=x", tmp_path)


def test_without_git_changes_cannot_be_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*args: object, **options: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(FileNotFoundError, match="git is not installed"):
        changed_since("HEAD", tmp_path)
