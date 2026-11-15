"""Observables: what a glob designates, where a path is anchored, and the built-in
observables (ADR-0028)."""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from jpipe_runner.observables import (
    HIDDEN,
    Context,
    Env,
    File,
    JsonValue,
    Observation,
    Sighting,
    files,
    matches,
    readable,
)


def _write(root: Path, path: str, content: bytes) -> Path:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)
    return file


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# --- What a glob designates ----------------------------------------------------------------


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


# --- Where a path is anchored --------------------------------------------------------------


@pytest.mark.parametrize(
    ("directory", "path", "shown"),
    [
        pytest.param(".", "CHANGELOG.md", "CHANGELOG.md", id="a library in the root"),
        pytest.param("justifications", "steps.log", "justifications/steps.log", id="beside it"),
        pytest.param("justifications", "../CHANGELOG.md", "CHANGELOG.md", id="above it"),
        pytest.param("a/b", "../../build/*.xml", "build/*.xml", id="a glob above it"),
        pytest.param("a", "**/*.md", "a/**/*.md", id="a glob from its directory"),
        pytest.param(".", "**/*.md", "**/*.md", id="a glob from the root"),
        pytest.param("..", "x.txt", "../x.txt", id="a library outside the root"),
    ],
)
def test_a_path_is_relative_to_the_declaring_file_and_shown_relative_to_the_root(
    tmp_path: Path, directory: str, path: str, shown: str
) -> None:
    root = tmp_path / "project"
    root.mkdir()

    assert Context(root / directory, root).shown(path) == shown


def test_a_library_observes_the_same_files_wherever_the_runner_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "justifications"
    _write(tmp_path, "CHANGELOG.md", b"## 2.0\n")
    library.mkdir()
    changelog = File("../CHANGELOG.md")

    monkeypatch.chdir(tmp_path)
    from_the_root = changelog.observe(Context(Path("justifications"), Path()))
    monkeypatch.chdir(library)
    from_the_library = changelog.observe(Context(Path(), Path()))

    assert from_the_root.value == Path("CHANGELOG.md")
    assert from_the_library.value == Path("../CHANGELOG.md")
    assert [o.sha256 for o in from_the_root.observations] == [_sha256(b"## 2.0\n")]
    assert [o.sha256 for o in from_the_library.observations] == [_sha256(b"## 2.0\n")]


@pytest.mark.skipif(sys.platform == "win32", reason="symbolic links need privileges on Windows")
def test_a_link_to_the_library_directory_is_followed_to_find_the_root(tmp_path: Path) -> None:
    (tmp_path / "project" / "lib").mkdir(parents=True)
    (tmp_path / "link").symlink_to(tmp_path / "project" / "lib")

    assert Context(tmp_path / "link", tmp_path / "project").shown("a.txt") == "lib/a.txt"


def test_without_a_relative_path_a_file_is_shown_where_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def another_drive(path: str, start: str) -> str:
        raise ValueError("path is on mount 'C:', start on mount 'D:'")

    monkeypatch.setattr(os.path, "relpath", another_drive)

    shown = Context(tmp_path, tmp_path).shown("a.txt")

    assert shown == (Path(os.path.realpath(tmp_path)) / "a.txt").as_posix()


# --- File ----------------------------------------------------------------------------------


def test_a_file_is_what_a_change_to_reaches_and_how_it_is_described(tmp_path: Path) -> None:
    context = Context(tmp_path / "lib", tmp_path)

    assert File("../build/*.xml").describe(context) == "build/*.xml"
    assert File("../build/*.xml").depends_on(context) == ("build/*.xml",)


def test_a_file_named_as_its_glob_is_a_file_not_a_glob_that_matched_nothing(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "*.txt", b"x")

    sighting = File("*.txt").observe(Context(tmp_path, tmp_path))

    assert sighting.observations == (Observation("*.txt", "*.txt", _sha256(b"x"), 1),)


# --- JsonValue -----------------------------------------------------------------------------

PACKAGE = {"version": "2.0", "authors": [{"name": "Ada"}], "a/b": {"~": 1}}


@pytest.mark.parametrize(
    ("pointer", "value"),
    [
        ("/version", "2.0"),
        ("/authors/0/name", "Ada"),
        ("/a~1b/~0", 1),
        ("", PACKAGE),
    ],
)
def test_a_json_value_is_designated_by_a_pointer(
    tmp_path: Path, pointer: str, value: object
) -> None:
    content = json.dumps(PACKAGE).encode()
    _write(tmp_path, "package.json", content)

    sighting = JsonValue("package.json", pointer).observe(Context(tmp_path, tmp_path))

    assert sighting.value == value
    assert sighting.observations == (
        Observation(
            f"package.json#{pointer}", "package.json", _sha256(content), len(content), value=value
        ),
    )


def test_a_json_value_depends_on_its_file(tmp_path: Path) -> None:
    context = Context(tmp_path / "lib", tmp_path)

    assert JsonValue("../package.json", "/version").describe(context) == "package.json#/version"
    assert JsonValue("../package.json", "/version").depends_on(context) == ("package.json",)


@pytest.mark.parametrize(
    ("content", "pointer", "what", "problem"),
    [
        pytest.param(None, "/version", "package.json", "does not exist", id="no file"),
        pytest.param(
            b"{", "/version", "package.json#/version", "cannot be read as JSON", id="not JSON"
        ),
        pytest.param(
            b"{}", "/version", "package.json#/version", "designates no value", id="no key"
        ),
        pytest.param(b"[1]", "/3", "package.json#/3", "designates no value", id="no index"),
        pytest.param(b"[1]", "/x", "package.json#/x", "designates no value", id="not an index"),
        pytest.param(b'"a"', "/x", "package.json#/x", "designates no value", id="a scalar"),
    ],
)
def test_a_json_value_that_cannot_be_reached_says_why(
    tmp_path: Path, content: bytes | None, pointer: str, what: str, problem: str
) -> None:
    if content is not None:
        _write(tmp_path, "package.json", content)

    (observation,) = (
        JsonValue("package.json", pointer).observe(Context(tmp_path, tmp_path)).observations
    )

    assert observation.obstacle is not None
    assert (observation.declared, observation.path) == (f"package.json#{pointer}", "package.json")
    assert observation.obstacle.what == what
    assert problem in observation.obstacle.problem
    assert observation.sha256 is None


@pytest.mark.parametrize(
    ("path", "pointer", "problem"),
    [
        ("*.json", "/version", "one file"),
        ("package.json", "version", "JSON Pointer"),
        ("/etc/package.json", "", "relative"),
    ],
)
def test_a_malformed_json_value_is_a_type_error(path: str, pointer: str, problem: str) -> None:
    with pytest.raises(TypeError, match=problem):
        JsonValue(path, pointer)


# --- Env -----------------------------------------------------------------------------------


def test_a_variable_is_not_shown_unless_it_may_be(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TOKEN", "s3cret")
    context = Context(tmp_path, tmp_path)

    hidden = Env("TOKEN").observe(context)
    shown = Env("TOKEN", display=True).observe(context)

    assert (hidden.value, shown.value) == ("s3cret", "s3cret")
    assert hidden.observations == (Observation("env:TOKEN", variable="TOKEN", hidden=True),)
    assert hidden.observations[0].value is HIDDEN
    assert repr(HIDDEN) == "HIDDEN"
    assert shown.observations == (
        Observation("env:TOKEN", sha256=_sha256(b'"s3cret"'), value="s3cret", variable="TOKEN"),
    )


def test_a_variable_that_is_not_set_is_unreachable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TOKEN", raising=False)

    (observation,) = Env("TOKEN").observe(Context(tmp_path, tmp_path)).observations

    assert not observation.reachable
    assert observation.obstacle is not None
    assert observation.obstacle.what == "the environment variable 'TOKEN'"
    assert observation.variable == "TOKEN"
    assert Env("TOKEN").depends_on(Context(tmp_path, tmp_path)) == ()


@pytest.mark.parametrize("name", ["", " ", "A=B", 3])
def test_a_malformed_variable_name_is_a_type_error(name: object) -> None:
    with pytest.raises(TypeError, match="environment variable"):
        Env(name)  # type: ignore[arg-type]


# --- Sighting ------------------------------------------------------------------------------


def test_whatever_is_observed_is_recorded_or_said_to_be_hidden() -> None:
    assert Sighting.of("clock", 12).observations == (
        Observation("clock", sha256=_sha256(b"12"), value=12),
    )
    assert Sighting.of("clock", 12, display=False).observations == (
        Observation("clock", hidden=True),
    )
    with pytest.raises(ValueError, match="at least one observation"):
        Sighting(12, ())
    with pytest.raises(ValueError, match="one of the two"):
        Observation("clock")
    with pytest.raises(ValueError, match="one of the two"):
        Observation("clock", sha256="0" * 64, hidden=True)
    with pytest.raises(ValueError, match="shows a value"):
        Observation("clock", hidden=True, value=12)


def test_a_sighting_of_a_value_that_is_not_json_is_fingerprinted_by_its_repr() -> None:
    sighting = Sighting.of("clock", {1, 2})

    assert sighting.observations[0].sha256 == _sha256(repr({1, 2}).encode())
