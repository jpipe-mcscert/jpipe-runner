"""Observing the artifacts of an evidence: recorded and injected, or JP019."""

import hashlib
import os
import sys
from pathlib import Path

import pytest

from jpipe_runner.artifacts import UNREACHABLE_ARTIFACT, observe
from jpipe_runner.diagnostics import Severity
from jpipe_runner.observables import (
    Context,
    Env,
    File,
    JsonValue,
    Observable,
    Observation,
    Sighting,
)
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
    artifact = Artifact("changelog", File("mock/CHANGELOG.md"))

    observed = observe([artifact], Context(tmp_path, tmp_path), ELEMENT)

    assert observed.reachable
    assert observed.diagnostics == ()
    assert observed.arguments == {"changelog": file}
    assert observed.observations == (
        Observation("mock/CHANGELOG.md", "mock/CHANGELOG.md", _sha256(b"## 2.0\n"), 7),
    )


def test_a_glob_passes_the_sorted_files_it_matches_and_records_each(tmp_path: Path) -> None:
    b = _write(tmp_path, "build/b.xml", b"<b/>")
    a = _write(tmp_path, "build/a.xml", b"<a/>")
    _write(tmp_path, "build/c.txt", b"not matched")
    (tmp_path / "build" / "d.xml").mkdir()
    artifact = Artifact("reports", File("build/*.xml"))

    observed = observe([artifact], Context(tmp_path, tmp_path), ELEMENT)

    assert observed.reachable
    assert observed.arguments == {"reports": [a, b]}
    assert [(o.path, o.sha256, o.size) for o in observed.observations] == [
        ("build/a.xml", _sha256(b"<a/>"), 4),
        ("build/b.xml", _sha256(b"<b/>"), 4),
    ]


def test_a_recursive_glob_matches_files_at_every_depth(tmp_path: Path) -> None:
    _write(tmp_path, "src/a.py", b"")
    _write(tmp_path, "src/pkg/b.py", b"")

    observed = observe(
        [Artifact("sources", File("src/**/*.py"))], Context(tmp_path, tmp_path), ELEMENT
    )

    assert [o.path for o in observed.observations] == ["src/a.py", "src/pkg/b.py"]


def test_an_empty_file_is_reachable(tmp_path: Path) -> None:
    _write(tmp_path, "empty.txt", b"")

    observed = observe([Artifact("empty", File("empty.txt"))], Context(tmp_path, tmp_path), ELEMENT)

    assert observed.reachable
    assert observed.observations[0].size == 0


def test_every_artifact_is_observed_in_the_order_declared(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", b"a")
    _write(tmp_path, "b.txt", b"b")
    artifacts = [Artifact("second", File("b.txt")), Artifact("first", File("a.txt"))]

    observed = observe(artifacts, Context(tmp_path, tmp_path), ELEMENT)

    assert [o.declared for o in observed.observations] == ["b.txt", "a.txt"]
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
    artifact = Artifact("a", File(path))

    observed = observe([artifact], Context(tmp_path, tmp_path), ELEMENT)

    assert not observed.reachable
    assert [(d.code, d.severity, d.element) for d in observed.diagnostics] == [
        (UNREACHABLE_ARTIFACT, Severity.ERROR, ELEMENT)
    ]
    (observation,) = observed.observations
    assert (observation.declared, observation.path) == (recorded, recorded)
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
        observed = observe(
            [Artifact("secret", File("secret.txt"))], Context(tmp_path, tmp_path), ELEMENT
        )
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
        [Artifact("link", File("link.txt")), Artifact("broken", File("broken.txt"))],
        Context(tmp_path, tmp_path),
        ELEMENT,
    )

    assert [o.sha256 for o in observed.observations] == [_sha256(b"content"), None]
    assert len(observed.diagnostics) == 1


def test_every_unreachable_artifact_is_reported_and_the_others_recorded(tmp_path: Path) -> None:
    _write(tmp_path, "there.txt", b"x")
    artifacts = [
        Artifact("a", File("missing.txt")),
        Artifact("b", File("there.txt")),
        Artifact("c", File("none/*.xml")),
    ]

    observed = observe(artifacts, Context(tmp_path, tmp_path), ELEMENT)

    assert len(observed.diagnostics) == 2
    assert [o.reachable for o in observed.observations] == [False, True, False]


def test_nothing_to_observe_is_reachable(tmp_path: Path) -> None:
    observed = observe([], Context(tmp_path, tmp_path), ELEMENT)

    assert observed.reachable
    assert observed.observations == ()
    assert observed.arguments == {}


def test_the_arguments_are_read_only(tmp_path: Path) -> None:
    _write(tmp_path, "a.txt", b"a")
    observed = observe([Artifact("a", File("a.txt"))], Context(tmp_path, tmp_path), ELEMENT)

    with pytest.raises(TypeError):
        observed.arguments["a"] = tmp_path  # type: ignore[index]


@pytest.mark.skipif(sys.platform == "win32", reason="named pipes are POSIX")
def test_a_named_pipe_is_unreachable_and_never_opened(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")

    observed = observe(
        [Artifact("pipe", File("pipe")), Artifact("pipes", File("pip*"))],
        Context(tmp_path, tmp_path),
        ELEMENT,
    )

    assert [d.code for d in observed.diagnostics] == [UNREACHABLE_ARTIFACT] * 2
    assert [o.reachable for o in observed.observations] == [False, False]


# --- Observables of a step library ---------------------------------------------------------


class Raises(Observable):
    def describe(self, context: Context) -> str:
        return "raises"

    def observe(self, context: Context) -> Sighting:
        raise RuntimeError("no network")


class Answers(Observable):
    def describe(self, context: Context) -> str:
        return "answers"

    def observe(self, context: Context) -> Sighting:
        return 42  # type: ignore[return-value]


def test_an_observable_that_raises_is_unreachable(tmp_path: Path) -> None:
    observed = observe([Artifact("a", Raises())], Context(tmp_path, tmp_path), ELEMENT)

    assert [d.message for d in observed.diagnostics] == [
        "a Raises, observed as 'a', could not be observed: it raised RuntimeError: no network"
    ]


def test_an_observable_that_raises_is_recorded_under_what_it_describes_itself_as(
    tmp_path: Path,
) -> None:
    """So that the observation is one of the element's sources, as the report says."""
    observed = observe([Artifact("a", Raises())], Context(tmp_path, tmp_path), ELEMENT)

    assert [seen.declared for seen in observed.observations] == ["raises"]


class Exits(Raises):
    def observe(self, context: Context) -> Sighting:
        raise SystemExit(0)


def test_an_observable_that_exits_is_unreachable_and_the_run_goes_on(tmp_path: Path) -> None:
    """sys.exit() in a library's observable must not end the run without a verdict."""
    observed = observe([Artifact("a", Exits())], Context(tmp_path, tmp_path), ELEMENT)

    assert [d.message for d in observed.diagnostics] == [
        "a Exits, observed as 'a', could not be observed: it raised SystemExit: 0"
    ]


def test_what_the_step_does_to_a_value_does_not_change_what_was_recorded(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "package.json", b'{"authors": ["ada"]}')
    artifact = Artifact("authors", JsonValue("package.json", "/authors"))

    observed = observe([artifact], Context(tmp_path, tmp_path), ELEMENT)
    observed.arguments["authors"].append("mallory")

    assert [seen.value for seen in observed.observations] == [["ada"]]


class Nameless(Raises):
    def describe(self, context: Context) -> str:
        raise KeyError("name")


def test_an_observable_that_cannot_describe_itself_is_named_after_its_class(
    tmp_path: Path,
) -> None:
    observed = observe([Artifact("a", Nameless())], Context(tmp_path, tmp_path), ELEMENT)

    assert [seen.declared for seen in observed.observations] == ["Nameless"]
    assert len(observed.diagnostics) == 1


def test_an_observable_that_answers_no_sighting_is_unreachable(tmp_path: Path) -> None:
    observed = observe([Artifact("a", Answers())], Context(tmp_path, tmp_path), ELEMENT)

    assert [d.message for d in observed.diagnostics] == [
        "answers, observed as 'a', could not be observed: it returned int, not a Sighting"
    ]


def test_files_and_other_observables_are_observed_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STAGE", "prod")
    file = _write(tmp_path, "a.txt", b"a")
    artifacts = [Artifact("stage", Env("STAGE", display=True)), Artifact("a", File("a.txt"))]

    observed = observe(artifacts, Context(tmp_path, tmp_path), ELEMENT)

    assert observed.arguments == {"stage": "prod", "a": file}
    assert [(o.declared, o.path) for o in observed.observations] == [
        ("env:STAGE", None),
        ("a.txt", "a.txt"),
    ]


def test_the_message_names_what_could_not_be_reached(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    artifacts = [
        Artifact("a", File("missing.txt")),
        Artifact("b", File("none/*.xml")),
        Artifact("c", File("src")),
        Artifact("d", Env("JPIPE_RUNNER_NOT_SET")),
    ]

    observed = observe(artifacts, Context(tmp_path, tmp_path), ELEMENT)

    assert [d.message for d in observed.diagnostics] == [
        "missing.txt, observed as 'a', does not exist",
        "the glob 'none/*.xml', observed as 'b', matches no file",
        "src, observed as 'c', is a directory, and evidence observes files",
        "the environment variable 'JPIPE_RUNNER_NOT_SET', observed as 'd', is not set",
    ]
