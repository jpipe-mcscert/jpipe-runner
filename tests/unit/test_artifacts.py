"""Observing the artifacts of an evidence: reached, recorded and injected, or JP019."""

import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from jpipe_runner.artifacts import (
    UNREACHABLE_ARTIFACT,
    Observation,
    files,
    locate,
    matches,
    observe,
    readable,
    record,
    unreachable,
)
from jpipe_runner.diagnostics import Severity
from jpipe_runner.steps import Artifact

ELEMENT = "m:e"


def _write(root: Path, path: str, content: bytes) -> Path:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)
    return file


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_a_file_is_recorded_and_passed_as_a_path(tmp_path: Path) -> None:
    file = _write(tmp_path, "mock/CHANGELOG.md", b"## 2.0\n")
    artifact = Artifact("changelog", "mock/CHANGELOG.md")

    observed = observe([artifact], tmp_path, ELEMENT)

    assert observed.reachable
    assert observed.diagnostics == ()
    assert observed.arguments == {"changelog": file}
    assert observed.observations == (
        Observation(artifact, "mock/CHANGELOG.md", _sha256(b"## 2.0\n"), 7),
    )


def test_a_glob_passes_the_sorted_files_it_matches_and_records_each(tmp_path: Path) -> None:
    b = _write(tmp_path, "build/b.xml", b"<b/>")
    a = _write(tmp_path, "build/a.xml", b"<a/>")
    _write(tmp_path, "build/c.txt", b"not matched")
    (tmp_path / "build" / "d.xml").mkdir()
    artifact = Artifact("reports", "build/*.xml")

    observed = observe([artifact], tmp_path, ELEMENT)

    assert observed.reachable
    assert observed.arguments == {"reports": [a, b]}
    assert [(o.path, o.sha256, o.size) for o in observed.observations] == [
        ("build/a.xml", _sha256(b"<a/>"), 4),
        ("build/b.xml", _sha256(b"<b/>"), 4),
    ]


def test_a_recursive_glob_matches_files_at_every_depth(tmp_path: Path) -> None:
    _write(tmp_path, "src/a.py", b"")
    _write(tmp_path, "src/pkg/b.py", b"")

    observed = observe([Artifact("sources", "src/**/*.py")], tmp_path, ELEMENT)

    assert [o.path for o in observed.observations] == ["src/a.py", "src/pkg/b.py"]


def test_an_empty_file_is_reachable(tmp_path: Path) -> None:
    _write(tmp_path, "empty.txt", b"")

    observed = observe([Artifact("empty", "empty.txt")], tmp_path, ELEMENT)

    assert observed.reachable
    assert observed.observations[0].size == 0


def test_every_artifact_is_observed_in_the_order_declared(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", b"a")
    _write(tmp_path, "b.txt", b"b")
    artifacts = [Artifact("second", "b.txt"), Artifact("first", "a.txt")]

    observed = observe(artifacts, tmp_path, ELEMENT)

    assert [o.artifact for o in observed.observations] == artifacts
    assert list(observed.arguments) == ["second", "first"]


@pytest.mark.parametrize(
    ("path", "recorded"),
    [
        pytest.param("missing.txt", "missing.txt", id="a missing file"),
        pytest.param("missing/*.xml", "missing/*.xml", id="a glob that matches nothing"),
        pytest.param("src", "src", id="a directory"),
    ],
)
def test_an_unreachable_artifact_is_jp019_and_recorded_without_a_digest(
    tmp_path: Path, path: str, recorded: str
) -> None:
    (tmp_path / "src").mkdir()
    artifact = Artifact("a", path)

    observed = observe([artifact], tmp_path, ELEMENT)

    assert not observed.reachable
    assert [(d.code, d.severity, d.element) for d in observed.diagnostics] == [
        (UNREACHABLE_ARTIFACT, Severity.ERROR, ELEMENT)
    ]
    (observation,) = observed.observations
    assert (observation.artifact, observation.path) == (artifact, recorded)
    assert (observation.sha256, observation.size) == (None, None)
    assert not observation.reachable
    assert observation.obstacle is not None


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions, not as root"
)
def test_an_unreadable_file_is_unreachable(tmp_path: Path) -> None:
    file = _write(tmp_path, "secret.txt", b"x")
    file.chmod(0)
    try:
        observed = observe([Artifact("secret", "secret.txt")], tmp_path, ELEMENT)
    finally:
        file.chmod(0o600)

    assert [d.code for d in observed.diagnostics] == [UNREACHABLE_ARTIFACT]
    assert observed.observations[0].sha256 is None


@pytest.mark.skipif(sys.platform == "win32", reason="symbolic links need privileges on Windows")
def test_a_broken_symbolic_link_is_unreachable_and_a_working_one_is_followed(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "target.txt", b"content")
    (tmp_path / "link.txt").symlink_to(tmp_path / "target.txt")
    (tmp_path / "broken.txt").symlink_to(tmp_path / "nowhere.txt")

    observed = observe(
        [Artifact("link", "link.txt"), Artifact("broken", "broken.txt")], tmp_path, ELEMENT
    )

    assert [o.sha256 for o in observed.observations] == [_sha256(b"content"), None]
    assert len(observed.diagnostics) == 1


def test_every_unreachable_artifact_is_reported_and_the_others_recorded(tmp_path: Path) -> None:
    _write(tmp_path, "there.txt", b"x")
    artifacts = [
        Artifact("a", "missing.txt"),
        Artifact("b", "there.txt"),
        Artifact("c", "none/*.xml"),
    ]

    observed = observe(artifacts, tmp_path, ELEMENT)

    assert len(observed.diagnostics) == 2
    assert [o.reachable for o in observed.observations] == [False, True, False]


def test_nothing_to_observe_is_reachable(tmp_path: Path) -> None:
    observed = observe([], tmp_path, ELEMENT)

    assert observed.reachable
    assert observed.observations == ()
    assert observed.arguments == {}


def test_the_arguments_are_read_only(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", b"a")
    observed = observe([Artifact("a", "a.txt")], tmp_path, ELEMENT)

    with pytest.raises(TypeError):
        observed.arguments["a"] = tmp_path  # type: ignore[index]


@pytest.mark.skipif(sys.platform == "win32", reason="named pipes are POSIX")
def test_a_named_pipe_is_unreachable_and_never_opened(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")

    observed = observe([Artifact("pipe", "pipe"), Artifact("pipes", "pip*")], tmp_path, ELEMENT)

    assert [d.code for d in observed.diagnostics] == [UNREACHABLE_ARTIFACT] * 2
    assert [o.reachable for o in observed.observations] == [False, False]


# --- What a glob designates --------------------------------------------------------------


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
        ("d", "d/**", False),  # and not what it is below
    ],
)
def test_a_path_matches_as_a_glob_designates_it(path: str, pattern: str, expected: bool) -> None:
    assert matches(path, pattern) is expected


_SEGMENTS = st.sampled_from(["a", "b", ".c", "a.txt", "b.md"])
_PATTERN_SEGMENTS = st.sampled_from(["*", "**", "a", "a.txt", "*.txt", "?", "[ab]", ".*"])


@settings(deadline=None)
@given(
    paths_parts=st.lists(st.lists(_SEGMENTS, min_size=1, max_size=3), min_size=1, max_size=6),
    pattern=st.lists(_PATTERN_SEGMENTS, min_size=1, max_size=3),
)
def test_matches_agrees_with_the_files_a_glob_lists(
    paths_parts: list[list[str]], pattern: list[str]
) -> None:
    paths = {"/".join(parts) for parts in paths_parts}
    # A path cannot be both a file and a directory.
    assume(not any(other.startswith(f"{path}/") for path in paths for other in paths))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for path in paths:
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text("x", encoding="utf-8")
        listed = {found.relative_to(root).as_posix() for found in files("/".join(pattern), root)}

    assert {path for path in paths if matches(path, "/".join(pattern))} == listed


def test_a_trailing_recursive_glob_lists_the_files_below_on_every_python(tmp_path: Path) -> None:
    a = _write(tmp_path, "src/a.py", b"")
    b = _write(tmp_path, "src/pkg/b.py", b"")

    assert files("src/**", tmp_path) == [a, b]


def test_a_glob_lists_regular_files_only_sorted(tmp_path: Path) -> None:
    b = _write(tmp_path, "build/b.xml", b"")
    a = _write(tmp_path, "build/a.xml", b"")
    (tmp_path / "build" / "d.xml").mkdir()

    assert files("build/*.xml", tmp_path) == [a, b]


# --- Located, recorded, injected: each on its own ------------------------------------------


def test_locating_reads_nothing_and_says_what_the_step_receives(tmp_path: Path) -> None:
    a = _write(tmp_path, "build/a.xml", b"<a/>")
    a.chmod(0)  # locating a file that cannot be read still finds it
    try:
        glob = locate(Artifact("reports", "build/*.xml"), tmp_path)
    finally:
        a.chmod(0o600)
    missing = locate(Artifact("log", "missing.log"), tmp_path)

    assert (glob.files, glob.argument) == ((a,), [a])
    assert (missing.files, missing.argument) == (
        (tmp_path / "missing.log",),
        tmp_path / "missing.log",
    )


def test_a_located_glob_that_matches_nothing_has_no_file(tmp_path: Path) -> None:
    located = locate(Artifact("reports", "build/*.xml"), tmp_path)

    assert (located.files, located.argument) == ((), [])


def test_recording_hashes_each_located_file(tmp_path: Path) -> None:
    _write(tmp_path, "build/a.xml", b"<a/>")
    artifact = Artifact("reports", "build/*.xml")

    assert record(locate(artifact, tmp_path), tmp_path) == (
        Observation(artifact, "build/a.xml", _sha256(b"<a/>"), 4),
    )


def test_what_was_not_reached_says_why_and_becomes_jp019(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    artifacts = [Artifact("a", "missing.txt"), Artifact("b", "none/*.xml"), Artifact("c", "src")]

    observations = [o for a in artifacts for o in record(locate(a, tmp_path), tmp_path)]

    assert [d.message for d in unreachable(observations, ELEMENT)] == [
        "missing.txt, observed as 'a', does not exist",
        "the glob 'none/*.xml', observed as 'b', matches no file",
        "src, observed as 'c', is a directory, and evidence observes files",
    ]
    assert [o.obstacle.what for o in observations if o.obstacle] == [
        "missing.txt",
        "the glob 'none/*.xml'",
        "src",
    ]


def test_a_file_named_as_its_glob_is_a_file_not_a_glob_that_matched_nothing(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "*.txt", b"x")
    artifact = Artifact("notes", "*.txt")

    (observation,) = record(locate(artifact, tmp_path), tmp_path)

    assert observation == Observation(artifact, "*.txt", _sha256(b"x"), 1)


def test_reachable_observations_have_no_diagnostic(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", b"a")

    observations = record(locate(Artifact("a", "a.txt"), tmp_path), tmp_path)

    assert unreachable(observations, ELEMENT) == ()


def test_readable_says_whether_a_file_can_be_observed_without_hashing_it(tmp_path: Path) -> None:
    file = _write(tmp_path, "a.txt", b"a")
    (tmp_path / "src").mkdir()

    assert readable(file)
    assert not readable(tmp_path / "missing.txt")
    assert not readable(tmp_path / "src")


@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="needs POSIX permissions, not as root"
)
def test_a_file_that_cannot_be_opened_is_not_readable(tmp_path: Path) -> None:
    file = _write(tmp_path, "secret.txt", b"x")
    file.chmod(0)
    try:
        assert not readable(file)
    finally:
        file.chmod(0o600)
