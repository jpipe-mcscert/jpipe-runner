"""Impact and staleness, from a JSON report (#146, ADR-0025)."""

import hashlib
import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from jpipe_runner import impact, json_report
from jpipe_runner.engine import Verdict
from jpipe_runner.impact import (
    Change,
    ChangeKind,
    Impact,
    InvalidReportError,
    Unchecked,
    Unverified,
    above,
    affected,
    changed_since,
    read,
    render_impact,
    render_stale,
    stale,
    unverified,
)
from jpipe_runner.model import Kind
from jpipe_runner.observables import fingerprint
from jpipe_runner.report import ElementReport, RunReport

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


def test_a_glob_no_file_was_recorded_under_finds_nothing_added(root: Path) -> None:
    """A library's observable may depend on a glob, for impact, and record no file under it:
    the files it matches were never the run's to see."""
    (root / "docs" / "b.md").write_text("B", encoding="utf-8")
    seen = {**_artifact("build/tests.log", "ok"), "declared": "build/tests.log"}
    document = _recorded(
        _element("e1", observes=["build/tests.log", "docs/*.md"], artifacts=[seen])
    )

    assert stale(document, root) == ()


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


def test_a_file_the_run_could_not_read_has_not_appeared_while_it_is_still_missing(
    root: Path,
) -> None:
    document = _recorded(
        _element("e1", observes=["build/gone.log"], artifacts=[_artifact("build/gone.log", None)])
    )

    assert stale(document, root) == ()


def test_a_file_the_run_could_not_read_has_not_appeared_while_it_still_cannot_be(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(file: Path, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError(f"{file}: permission denied")

    monkeypatch.setattr(Path, "open", unreadable)
    document = _recorded(
        _element("e1", observes=["build/tests.log"], artifacts=[_artifact("build/tests.log", None)])
    )

    assert stale(document, root) == ()


def _read_not_found(path: str, content: str) -> dict[str, Any]:
    """A file the run read without finding what it observed in it, such as a value a JSON
    Pointer designates."""
    read = _artifact(path, content)
    return _artifact(path, None) | {
        "declared": f"{path}#/version",
        "read": {"sha256": read["sha256"], "size": read["size"]},
    }


@pytest.mark.parametrize(
    ("artifact", "kind"),
    [
        pytest.param(_read_not_found("build/tests.log", "ok"), None, id="as it was"),
        pytest.param(_read_not_found("build/tests.log", "x"), ChangeKind.CHANGED, id="changed"),
        pytest.param(_read_not_found("build/gone.log", "ok"), ChangeKind.VANISHED, id="vanished"),
    ],
)
def test_a_file_read_without_finding_what_it_designates_is_compared_by_its_sha256(
    artifact: dict[str, Any], kind: ChangeKind | None, root: Path
) -> None:
    """#166: it has not appeared, since the run read it."""
    document = _recorded(_element("e1", observes=[artifact["path"]], artifacts=[artifact]))

    expected = () if kind is None else (Change("e1", artifact["path"], kind),)
    assert stale(document, root) == expected


def test_a_file_under_a_directory_named_with_a_wildcard_is_matched_escaped(root: Path) -> None:
    """#167: the report escapes the wildcards of the directory it puts in front of a path."""
    (root / "checks[v2]").mkdir()
    (root / "checks[v2]" / "a.md").write_text("A", encoding="utf-8")
    (root / "checks[v2]" / "b.md").write_text("B", encoding="utf-8")
    document = _recorded(
        *(
            _element(
                element,
                supports=["c"],
                observes=[pattern],
                artifacts=[_artifact("checks[v2]/a.md", "A") | {"declared": pattern}],
            )
            for element, pattern in [("e1", "checks[[]v2]/a.md"), ("e2", "checks[[]v2]/*.md")]
        ),
        _element("c", "conclusion"),
    )

    assert affected(document, ["checks[v2]/a.md"]).evidence == ("e1", "e2")
    assert affected(document, ["checks[v2]/b.md"]).evidence == ("e2",)
    assert affected(document, ["checksv/a.md"]).evidence == ()
    assert stale(document, root) == (Change("e2", "checks[v2]/b.md", ChangeKind.ADDED),)


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
        pytest.param('{"schema_version": "3.0"}', id="a later major version"),
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
    major, _, minor = json_report.SCHEMA_VERSION.partition(".")
    document |= {"schema_version": f"{major}.{int(minor) + 1}", "duration": 3.5}
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
    document = {"schema_version": "2.1", "justification": "release", "elements": [element]}

    assert stale(document, root) == (Change("e1", "build/tests.log", ChangeKind.CHANGED),)


def test_a_report_of_version_1_is_read_with_the_dataflow_field_2_0_removed(
    tmp_path: Path,
) -> None:
    document = json.loads(json_report.dumps(RunReport("m", Verdict.PASS)))
    document |= {"schema_version": "1.1", "diagram": "m.svg", "dataflow": "m-dataflow.svg"}
    path = tmp_path / "report.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    assert read(path)["diagram"] == "m.svg"


def test_a_report_of_an_earlier_minor_version_is_read_without_the_fields_added_since(
    tmp_path: Path,
) -> None:
    report = RunReport("m", Verdict.PASS, (ElementReport("e", "e", Kind.EVIDENCE),))
    document = json.loads(json_report.dumps(report))
    document["schema_version"] = "1.0"
    document["elements"][0]["artifacts"] = [
        {"path": "a.txt", "reachable": True, "sha256": "0" * 64, "size": 1}
    ]
    path = tmp_path / "report.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    assert read(path)["elements"][0]["artifacts"][0]["path"] == "a.txt"


def test_an_unreadable_file_a_glob_matched_appears_even_if_its_name_holds_a_wildcard(
    root: Path,
) -> None:
    (root / "docs" / "a[1].md").write_text("A", encoding="utf-8")
    recorded = _artifact("docs/a[1].md", None) | {"declared": "docs/*.md"}
    seen = _artifact("docs/a.md", "A") | {"declared": "docs/*.md"}
    document = _recorded(_element("e2", observes=["docs/*.md"], artifacts=[recorded, seen]))

    assert stale(document, root) == (Change("e2", "docs/a[1].md", ChangeKind.APPEARED),)


def test_a_glob_of_escaped_wildcards_that_matched_nothing_finds_its_file_added(
    root: Path,
) -> None:
    """``File("[[]notes].md")`` designates ``[notes].md`` only, and is a glob all the same."""
    recorded = _artifact("[[]notes].md", None) | {"declared": "[[]notes].md"}
    document = _recorded(_element("e1", observes=["[[]notes].md"], artifacts=[recorded]))
    assert stale(document, root) == ()

    (root / "[notes].md").write_text("N", encoding="utf-8")

    assert stale(document, root) == (Change("e1", "[notes].md", ChangeKind.ADDED),)


def test_a_glob_recorded_as_matching_nothing_never_appears(root: Path) -> None:
    recorded = _artifact("docs/*.md", None) | {"declared": "docs/*.md"}
    document = _recorded(_element("e2", observes=["docs/*.md"], artifacts=[recorded]))

    assert stale(document, root) == (Change("e2", "docs/a.md", ChangeKind.ADDED),)


def _variable(name: str, value: str | None, *, hidden: bool = False) -> dict[str, Any]:
    """An environment variable as a run recorded it: ``value`` is None if it was not set."""
    shown = value is not None and not hidden
    return {
        "declared": f"env:{name}",
        "variable": name,
        "reachable": value is not None,
        "hidden": hidden,
        "sha256": fingerprint(value) if shown else None,
        "value": {"value": value} if shown else None,
    }


@pytest.mark.parametrize(
    ("recorded", "now", "kind"),
    [
        pytest.param("prod", "prod", None, id="as it was"),
        pytest.param("prod", "staging", ChangeKind.CHANGED, id="changed"),
        pytest.param("prod", None, ChangeKind.VANISHED, id="no longer set"),
        pytest.param(None, "prod", ChangeKind.APPEARED, id="set since"),
        pytest.param(None, None, None, id="still not set"),
    ],
)
def test_a_recorded_variable_is_compared_with_the_environment(
    root: Path, recorded: str | None, now: str | None, kind: ChangeKind | None
) -> None:
    document = _recorded(_element("e1") | {"observations": [_variable("STAGE", recorded)]})
    environment = {} if now is None else {"STAGE": now}

    expected = () if kind is None else (Change("e1", "env:STAGE", kind),)
    assert stale(document, root, environment) == expected
    assert unverified(document) == ()


def test_the_environment_is_the_process_s_by_default(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STAGE", "staging")
    document = _recorded(_element("e1") | {"observations": [_variable("STAGE", "prod")]})

    assert stale(document, root) == (Change("e1", "env:STAGE", ChangeKind.CHANGED),)


def test_what_is_hidden_or_only_a_library_can_observe_needs_a_new_run(root: Path) -> None:
    host = {
        "declared": "host:example.org",
        "variable": None,
        "reachable": True,
        "hidden": False,
        "sha256": "0" * 64,
        "value": {"value": "192.0.2.1"},
    }
    observations = [_variable("TOKEN", "s3cret", hidden=True), host, _variable("STAGE", "prod")]
    document = _recorded(
        _element("e1", supports=["c"]) | {"observations": observations},
        _element("c", "conclusion"),
    )

    # A hidden variable is never compared, whatever it is now.
    assert stale(document, root, {"STAGE": "prod", "TOKEN": "another"}) == ()
    unchecked = unverified(document)
    assert unchecked == (
        Unverified("e1", "env:TOKEN", Unchecked.HIDDEN),
        Unverified("e1", "host:example.org", Unchecked.UNREADABLE),
    )
    assert render_stale(document, (), unchecked) == (
        "Justification: release\n"
        "\n"
        "Information was hidden from the report, so it needs a new run:\n"
        "  env:TOKEN         e1\n"
        "\n"
        "Only its step library can observe it again, so it needs a new run:\n"
        "  host:example.org  e1\n"
        "\n"
        "Not confirmed (2 elements):\n"
        "  Evidence    The e1  # e1\n"
        "  Conclusion  The c   # c\n"
    )


def test_what_changed_is_listed_before_what_needs_a_new_run(root: Path) -> None:
    observations = [_variable("TOKEN", "s3cret", hidden=True)]
    document = _recorded(
        _element(
            "e1", observes=["build/tests.log"], artifacts=[_artifact("build/tests.log", "was")]
        )
        | {"observations": observations}
    )

    text = render_stale(document, stale(document, root), unverified(document))

    assert text.index("Changed since the run:") < text.index("Stale (1 elements):")
    assert text.index("Stale (1 elements):") < text.index("Information was hidden")
    assert "still holds" not in text


def test_a_report_of_version_1_0_has_nothing_that_cannot_be_checked() -> None:
    assert unverified(RELEASE) == ()


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
def test_a_renamed_file_is_changed_under_both_its_names(repository: Path) -> None:
    _git(repository, "mv", "kept.txt", "moved.txt")

    assert {"kept.txt", "moved.txt"} <= set(changed_since("HEAD", repository))


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


def test_a_path_that_is_not_utf8_is_listed_as_the_file_system_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # macOS refuses such names, so git's output is given rather than produced.
    def git(arguments: list[str], **options: object) -> subprocess.CompletedProcess[bytes]:
        listed = b"docs/caf\xe9.md\0" if "diff" in arguments else b""
        return subprocess.CompletedProcess(arguments, 0, listed, b"")

    monkeypatch.setattr(subprocess, "run", git)

    [changed] = changed_since("HEAD", tmp_path)

    assert changed == "docs/caf\udce9.md"
    assert affected(RELEASE, [changed]).evidence == ("e2",)
    assert "docs/caf\\xe9.md  e2" in render_impact(RELEASE, affected(RELEASE, [changed]))


def test_a_file_recorded_under_two_overlapping_paths_is_listed_once(root: Path) -> None:
    (root / "docs" / "b.md").write_text("B", encoding="utf-8")
    recorded = [_artifact("docs/a.md", "was A"), _artifact("docs/a.md", "was A")]
    document = _recorded(
        _element("e2", observes=["docs/*.md", "docs/a.md", "docs/**/*.md"], artifacts=recorded)
    )

    assert stale(document, root) == (
        Change("e2", "docs/a.md", ChangeKind.CHANGED),
        Change("e2", "docs/b.md", ChangeKind.ADDED),
    )


def test_the_current_major_version_of_the_report_is_read() -> None:
    # A new major of the report must be added to READ deliberately, keeping the earlier
    # ones impact and status can still read (#178).
    assert json_report.SCHEMA_VERSION.partition(".")[0] in impact.READ


@pytest.mark.parametrize("major", impact.READ)
def test_a_report_of_each_major_version_read_is_accepted(tmp_path: Path, major: str) -> None:
    document = json.loads(json_report.dumps(RunReport("m", Verdict.PASS)))
    document["schema_version"] = f"{major}.0"
    path = tmp_path / "report.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    assert read(path)["schema_version"] == f"{major}.0"
