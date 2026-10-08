"""Observing the artifacts of an evidence: reached, recorded and injected, or JP019."""

import hashlib
import os
import sys
from pathlib import Path

import pytest

from jpipe_runner.artifacts import UNREACHABLE_ARTIFACT, Observation, observe
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
    assert observed.observations == (Observation(artifact, recorded),)
    assert not observed.observations[0].reachable


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
