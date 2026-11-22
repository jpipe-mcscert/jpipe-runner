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
    DEFAULT_SHAPE,
    HIDDEN,
    SHAPES,
    Context,
    Env,
    File,
    JsonValue,
    Observable,
    Observation,
    Obstacle,
    Sighting,
    designates,
    designates_one,
    drawn_as,
    escape,
    files,
    matches,
    readable,
    unescape,
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
        ("checks[v2]/a.md", "checks[[]v2]/*.md", True),  # a wildcard escaped is itself
        ("checks[v2]/a.md", "checks[v2]/*.md", False),  # and is a wildcard otherwise
    ],
)
def test_a_path_matches_as_a_glob_designates_it(path: str, pattern: str, expected: bool) -> None:
    assert matches(path, pattern) is expected


_SEGMENTS = st.sampled_from(["a", "b", ".c", "a.txt", "b.md", "[a]"])
_PATTERN_SEGMENTS = st.sampled_from(
    ["*", "**", "a", "a.txt", "*.txt", "?", "[ab]", ".*", "[[]a]", "[[]*"]
)


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
        pytest.param("checks[v2]", "*.md", "checks[[]v2]/*.md", id="a wildcard escaped"),
        pytest.param("checks[v2]", "a.md", "checks[[]v2]/a.md", id="before a file too"),
        pytest.param("a*/b?", "../c.md", "a[*]/c.md", id="each wildcard"),
        pytest.param("checks[v2]", "../a[b].md", "a[b].md", id="not in what is declared"),
    ],
)
def test_a_path_is_relative_to_the_declaring_file_and_shown_relative_to_the_root(
    tmp_path: Path, directory: str, path: str, shown: str
) -> None:
    root = tmp_path / "project"
    root.mkdir()

    assert Context(root / directory, root).shown(path) == shown


@pytest.mark.parametrize("path", ["a.md", "checks[v2]/a.md", "x[*]/[[]/?*]", "[[]"])
def test_a_path_escaped_is_read_back_as_it_was(path: str) -> None:
    assert unescape(escape(path)) == path
    assert matches(path, escape(path))


@pytest.mark.parametrize(
    ("pattern", "one"),
    [
        ("a.md", True),
        ("app/[[]slug]/a.md", True),
        ("app/[[]slug]/*.md", False),
        ("a[*]b[?]", True),
        ("[ab].md", False),
        ("a[1].md", False),
    ],
)
def test_a_glob_whose_wildcards_are_all_escaped_designates_one_path(
    pattern: str, one: bool
) -> None:
    assert designates_one(pattern) is one


@pytest.mark.skipif(sys.platform == "win32", reason="'*' and '?' cannot be in a Windows name")
def test_a_library_in_a_directory_named_with_wildcards_observes_its_own_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#167: what is observed does not depend on where the runner runs."""
    library = tmp_path / "checks[v2]" / "*"
    _write(library, "a.md", b"A")
    _write(tmp_path, "checks[v2]/2.md", b"2")  # what the unescaped glob would match
    from_the_root = Context(library, tmp_path)

    (seen,) = File("*.md").observe(from_the_root).observations
    (literal,) = File("a.md").observe(from_the_root).observations

    assert (seen.declared, seen.path) == ("checks[[]v2]/[*]/*.md", "checks[v2]/*/a.md")
    assert (literal.declared, literal.path) == ("checks[[]v2]/[*]/a.md", "checks[v2]/*/a.md")
    assert seen.sha256 == literal.sha256 == _sha256(b"A")
    monkeypatch.chdir(library)
    assert File("*.md").observe(Context(Path(), Path())).value == [Path("a.md")]


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
        # RFC 6901: an index has no sign and no leading zero, and '-' is past the end.
        pytest.param(b"[1, 2]", "/-1", "package.json#/-1", "designates no value", id="negative"),
        pytest.param(b"[1, 2]", "/01", "package.json#/01", "designates no value", id="zero-led"),
        pytest.param(b"[1, 2]", "/+1", "package.json#/+1", "designates no value", id="signed"),
        pytest.param(b"[1, 2]", "/-", "package.json#/-", "designates no value", id="past the end"),
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
    # #166: a file that was read is recorded as it was, for status to compare.
    read = None if content is None else (_sha256(content), len(content))
    assert (None if observation.sha256 is None else (observation.sha256, observation.size)) == read


def test_a_json_value_in_a_directory_named_with_a_wildcard_is_read_there(tmp_path: Path) -> None:
    _write(tmp_path, "app[id]/package.json", b'{"version": "2.0"}')

    sighting = JsonValue("package.json", "/version").observe(
        Context(tmp_path / "app[id]", tmp_path)
    )

    assert sighting.value == "2.0"
    assert [(o.declared, o.path) for o in sighting.observations] == [
        ("app[[]id]/package.json#/version", "app[id]/package.json")
    ]


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


@pytest.mark.parametrize("path", [123, "", "/etc/package.json", "config/", "a/**b/c.json"])
def test_a_malformed_json_value_path_is_blamed_on_json_value(path: object) -> None:
    with pytest.raises(TypeError, match=r"^JsonValue\(\)"):
        JsonValue(path, "/version")  # type: ignore[arg-type]


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


def test_a_file_is_recorded_with_its_sha256_and_size_both_and_always_when_it_was_reached() -> None:
    """As the report's schema requires: a library's observable builds its own."""
    sha256 = _sha256(b"x")
    missing = Obstacle("x.bin", "does not exist")
    assert Observation("x", "x.bin", sha256, 1).reachable
    assert not Observation("x", "x.bin", obstacle=missing).reachable
    # Read, and what was observed in it not found.
    assert not Observation("x", "x.bin", sha256, 1, obstacle=missing).reachable
    with pytest.raises(ValueError, match="is a file, and is hidden"):
        Observation("x", "x.bin", hidden=True)
    with pytest.raises(ValueError, match="SHA-256 and size"):
        Observation("x", "x.bin", sha256=sha256)
    with pytest.raises(ValueError, match="SHA-256 and size"):
        Observation("x", "x.bin", sha256=sha256, obstacle=missing)


def test_a_sighting_of_a_value_that_is_not_json_is_fingerprinted_by_its_repr() -> None:
    sighting = Sighting.of("clock", {1, 2})

    assert sighting.observations[0].sha256 == _sha256(repr({1, 2}).encode())


# --- Shapes ---------------------------------------------------------------------------------


def test_each_built_in_says_the_shape_the_diagram_draws_it_in() -> None:
    assert File("CHANGELOG.md").shape == "tab"
    assert File("src/**/*.py").shape == "folder"
    assert JsonValue("package.json", "/version").shape == "component"
    assert Env("CI").shape == "house"
    assert {"tab", "folder", "component", "house", DEFAULT_SHAPE} <= SHAPES


class _Shaped(Observable):
    def __init__(self, shape: object) -> None:
        self._shape = shape

    @property
    def shape(self) -> str:
        if isinstance(self._shape, Exception):
            raise self._shape
        return self._shape  # type: ignore[return-value]

    def describe(self, context: Context) -> str:
        return "shaped"

    def observe(self, context: Context) -> Sighting:
        return Sighting.of("shaped", None)


@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        pytest.param("cylinder", "cylinder", id="one of SHAPES"),
        pytest.param("note", DEFAULT_SHAPE, id="an evidence's"),
        pytest.param("circle", DEFAULT_SHAPE, id="one that grows with its label"),
        pytest.param(RuntimeError("no"), DEFAULT_SHAPE, id="raises"),
    ],
)
def test_the_diagram_draws_an_observable_in_its_shape_or_the_default(
    shape: object, expected: str
) -> None:
    assert drawn_as(_Shaped(shape)) == expected


# --- What a path or a glob designates (ADR-0035) ---------------------------------------------


def test_a_path_designates_its_file_and_a_link_to_it(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    os.link(tmp_path / "a.txt", tmp_path / "linked.txt")

    assert designates("a.txt", tmp_path / "a.txt", tmp_path)
    assert designates("a.txt", tmp_path / "linked.txt", tmp_path)
    assert not designates("a.txt", tmp_path / "b.txt", tmp_path)


def test_a_glob_designates_a_file_by_name_before_it_exists(tmp_path: Path) -> None:
    assert designates("build/*.xml", tmp_path / "build" / "new.xml", tmp_path)
    assert not designates("build/*.xml", tmp_path / "build" / "new.json", tmp_path)


def test_a_glob_designates_nothing_outside_the_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    assert not designates("**/*.md", tmp_path / "outside.md", root)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symbolic links here")
def test_a_glob_designates_through_a_linked_directory_both_ways(tmp_path: Path) -> None:
    (tmp_path / "mock").mkdir()
    (tmp_path / "build").symlink_to(tmp_path / "mock", target_is_directory=True)

    assert designates("mock/*.md", tmp_path / "build" / "new.md", tmp_path)
    assert designates("build/*.md", tmp_path / "mock" / "new.md", tmp_path)


def test_a_glob_designates_a_link_to_a_file_it_matches(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "a.log").write_text("a", encoding="utf-8")
    os.link(tmp_path / "logs" / "a.log", tmp_path / "elsewhere.txt")

    assert designates("logs/*.log", tmp_path / "elsewhere.txt", tmp_path)
