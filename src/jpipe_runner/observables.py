"""Observables: what an evidence can observe of the world (ADR-0028).

An evidence declares what it observes, by parameter (ADR-0018). Each thing declared is an
``Observable``, which says three things:

- ``describe``: how the report names it;
- ``observe``: what it is now, as a ``Sighting``: the value the step receives, and an
  ``Observation`` of each thing seen, or the ``Obstacle`` that kept it from being seen;
- ``depends_on``: the files a change to which reaches it, for impact analysis.

Three are built in: ``File``, a file or a glob of files, which a bare string in
``observes`` stands for; ``JsonValue``, a value in a JSON file; and ``Env``, an
environment variable. A step library defines its own by deriving ``Observable``.

A path is written relative to the directory of the file that declares the step, so that a
library observes the same files wherever the runner is started. An ``Observable`` receives
a ``Context``, which turns such a path into one relative to the run's root, as the report
shows it. What the report shows is a glob: a wildcard in the name of a directory the
runner puts in front of the path is escaped, so that it designates that directory only.

What a glob designates is defined here, and nowhere else: ``files`` lists the files it
matches under a root, and ``matches`` says whether it would match a path, without the file
system. A property test holds them to the same answer.
"""

import copy
import hashlib
import json
import os
import posixpath
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import Any, Final

_CHUNK = 1 << 16
_INDEX = re.compile(r"0|[1-9]\d*", re.ASCII)
"""An array index in a JSON Pointer (RFC 6901): no sign, no leading zero."""
_EVIDENCE = "@evidence(observes=...)"
_RECURSIVE = "**"
_WILDCARDS = frozenset("*?[")
_ESCAPED = re.compile(r"\[([*?\[])\]")
"""A wildcard escaped, as ``escape`` writes it: alone in a character class."""

_MISSING_FIX = (
    "Make sure it exists when the runner runs. A path in observes={...} is relative to "
    "the file that declares the step."
)


class _Hidden:
    """The value of an observation that the report does not show."""

    def __repr__(self) -> str:
        return "HIDDEN"


HIDDEN: Final = _Hidden()
"""Stands for a value that was observed and is not shown."""


def is_glob(path: str) -> bool:
    """Whether ``path`` is a glob pattern, which may match several files, rather than a path."""
    return not _WILDCARDS.isdisjoint(path)


def escape(path: str) -> str:
    """``path`` as a glob that designates it, and nothing else: each wildcard alone in a
    character class, as ``glob.escape`` writes it."""
    return "".join(f"[{c}]" if c in _WILDCARDS else c for c in path)


def unescape(shown: str) -> str:
    """The path that ``shown``, written by ``escape``, designates."""
    return _ESCAPED.sub(r"\1", shown)


def matches(path: str, pattern: str) -> bool:
    """Whether the file at ``path`` is one that ``pattern`` designates, both relative to
    the root, as ``files`` lists them: each segment as ``fnmatch`` does, case sensitive,
    and ``**`` for any number of segments, none included, unless it ends the pattern: it
    is then the files below."""
    return _matches(PurePosixPath(path).parts, PurePosixPath(pattern).parts)


def _matches(parts: Sequence[str], pattern: Sequence[str]) -> bool:
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head == _RECURSIVE:
        if not rest:  # a trailing ** designates the files below: at least one segment
            return bool(parts)
        return any(_matches(parts[skipped:], rest) for skipped in range(len(parts) + 1))
    return bool(parts) and fnmatchcase(parts[0], head) and _matches(parts[1:], rest)


def files(pattern: str, root: Path) -> list[Path]:
    """The regular files under ``root`` that the glob ``pattern`` designates, sorted.

    ``Path.glob`` takes a trailing ``**`` for directories only before Python 3.13, and for
    the files below too from then on: here it is the files below, on every version.
    """
    if PurePosixPath(pattern).name == _RECURSIVE:
        pattern += "/*"
    return sorted(path for path in root.glob(pattern) if path.is_file())


def digest(file: Path) -> tuple[str, int]:
    """The SHA-256 of ``file``'s content, and its size in bytes, from one read."""
    hashed = hashlib.sha256()
    size = 0
    with file.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            hashed.update(chunk)
            size += len(chunk)
    return hashed.hexdigest(), size


def readable(file: Path) -> bool:
    """Whether ``file`` can be observed now: a regular file that can be opened. It is not
    read."""
    if _obstacle(file, str(file)) is not None:
        return False
    try:
        with file.open("rb"):
            return True
    except OSError:
        return False


@dataclass(frozen=True)
class Context:
    """Where an observation is made from."""

    directory: Path
    """The directory of the file that declares the step: what its paths are relative to."""
    root: Path
    """The run's root, the directory the runner runs in: what the report's paths are
    relative to."""

    def shown(self, path: str) -> str:
        """``path``, a path or a glob relative to ``directory``, as the report shows it:
        relative to ``root``, with ``/`` as separator. Links are followed to find where
        the two directories are, never in ``path`` itself.

        It is a glob, which ``impact`` and ``status`` match: a wildcard in the directories
        put in front of ``path`` is escaped, so that a library in ``checks[v2]/`` that
        observes ``*.md`` is shown ``checks[[]v2]/*.md``. Without one, nothing is."""
        parts = path.split("/")
        first = next((i for i, part in enumerate(parts) if is_glob(part)), len(parts))
        literal = os.path.normpath(os.path.join(os.path.realpath(self.directory), *parts[:first]))
        try:
            relative = PurePath(os.path.relpath(literal, os.path.realpath(self.root))).as_posix()
        except ValueError:  # on Windows, another drive: there is no relative path
            relative = PurePath(literal).as_posix()
        return "/".join(([] if relative == "." else [escape(relative)]) + parts[first:])

    def file(self, shown: str) -> Path:
        """The file at ``shown``, a path as ``shown`` writes it: the wildcards it escaped
        are read as the characters they are."""
        return self.root / unescape(shown)


@dataclass(frozen=True)
class Obstacle:
    """Why something could not be observed."""

    what: str
    """What could not be reached: a file's path, a glob that matched nothing, a variable."""
    problem: str
    fix: str = _MISSING_FIX


@dataclass(frozen=True)
class Observation:
    """One thing an evidence observed, as it was just before its step was called.

    Whatever was observed is recorded: an observation holds the SHA-256 of what was seen,
    or says that it is ``hidden``, or holds the ``obstacle`` that kept it from being seen.
    There is no fourth case, so that a report never passes over something a verdict rests
    on.

    A file has a ``path``, relative to the run's root, a SHA-256 and a size. An environment
    variable has its name, ``variable``. With one or the other, ``jpipe-runner status`` can
    look again without the step library; with neither, or when it is hidden, only a new
    run can. A glob that matches nothing is recorded once, under its pattern.
    """

    declared: str
    """What was declared that designates it, as its observable describes itself."""
    path: str | None = None
    sha256: str | None = None
    size: int | None = None
    obstacle: Obstacle | None = None
    value: Any = HIDDEN
    """What was observed there, or ``HIDDEN``: a file's content is never shown."""
    variable: str | None = None
    """The environment variable it is the value of, if it is one."""
    hidden: bool = False
    """Whether what was seen is kept out of the report, its SHA-256 included."""

    def __post_init__(self) -> None:
        recorded = self.sha256 is not None
        if self.obstacle is None and recorded == self.hidden:
            raise ValueError(
                f"the observation of {self.declared!r} records the SHA-256 of what was "
                "seen, or says that it is hidden: one of the two"
            )
        if self.hidden and self.value is not HIDDEN:
            raise ValueError(f"the observation of {self.declared!r} is hidden, and shows a value")
        if self.path is not None:
            self._check_file()

    def _check_file(self) -> None:
        """A file is never hidden, and is recorded with its SHA-256 and size exactly when
        it was reached, as the report's schema requires."""
        if self.hidden:
            raise ValueError(f"the observation of {self.declared!r} is a file, and is hidden")
        recorded = self.sha256 is not None and self.size is not None
        unrecorded = self.sha256 is None and self.size is None
        if not (recorded if self.obstacle is None else unrecorded):
            raise ValueError(
                f"the observation of the file {self.path!r} records its SHA-256 and size "
                "when it was reached, and neither when it was not"
            )

    @property
    def reachable(self) -> bool:
        return self.obstacle is None


@dataclass(frozen=True)
class Sighting:
    """What an observable is now: what the step receives, and what the report records."""

    value: Any
    """What the step receives. Unused when an observation has an obstacle."""
    observations: tuple[Observation, ...]
    """What the report records: at least one, since nothing is observed off the record."""

    def __post_init__(self) -> None:
        if not self.observations:
            raise ValueError("a sighting records at least one observation")

    @classmethod
    def of(cls, declared: str, value: Any, *, display: bool = True) -> "Sighting":
        """A value that was observed, and is no file. Unless ``display``, it is hidden:
        the report says only that it was observed, neither the value nor its SHA-256, and
        only a new run can tell whether it changed."""
        if not display:
            return cls(value, (Observation(declared, hidden=True),))
        return cls(value, (Observation(declared, sha256=fingerprint(value), value=value),))

    @classmethod
    def unreachable(
        cls, declared: str, what: str, problem: str, fix: str = _MISSING_FIX
    ) -> "Sighting":
        """Nothing could be observed: ``what`` has this ``problem``, and the step is not
        called."""
        return cls(None, (Observation(declared, obstacle=Obstacle(what, problem, fix)),))


def fingerprint(value: Any) -> str:
    """The SHA-256 of ``value`` written as JSON, or as its ``repr`` if it is not JSON."""
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


class Observable(ABC):
    """Something an evidence observes. Derive it to observe what no built-in does.

    An observable is declared once and observed at every run: it holds what designates the
    thing (a path, a name), never the thing. It must be hashable, as a frozen dataclass is.
    """

    @abstractmethod
    def describe(self, context: Context) -> str:
        """How the report names it. It says the same for the same run, wherever it runs."""

    @abstractmethod
    def observe(self, context: Context) -> Sighting:
        """What it is now. An exception it raises is reported as an obstacle."""

    def depends_on(self, context: Context) -> tuple[str, ...]:
        """The files, as paths or globs relative to the run's root, a change to which
        reaches it. None by default: impact analysis does not see it."""
        return ()


def snapshot(value: Any) -> Any:
    """A deep copy of ``value``, or ``value`` itself if it cannot be copied (a lock, an open
    file): what the report records stays as it was, whatever a step then does to it."""
    try:
        return copy.deepcopy(value)
    except Exception:  # deepcopy raises whatever the value's __deepcopy__ or __reduce__ does
        return value


def described(observable: Observable, context: Context) -> str:
    """How the report names ``observable``. One of a step library may raise: it is then
    named after its class, and observing it fails with the error it raises."""
    try:
        return observable.describe(context)
    # Whatever a library's observable raises, even SystemExit.
    except (Exception, SystemExit):  # NOSONAR
        return type(observable).__name__


def dependencies(observable: Observable, context: Context) -> tuple[str, ...]:
    """What ``observable`` depends on, or nothing if it raises: one of a step library may."""
    try:
        return tuple(observable.depends_on(context))
    # Whatever a library's observable raises, even SystemExit.
    except (Exception, SystemExit):  # NOSONAR
        return ()


@dataclass(frozen=True)
class File(Observable):
    """A file, or the files a glob matches. A bare string in ``observes`` stands for one.

    ``path`` is relative to the directory of the file that declares the step. The step
    receives a ``Path``, or the sorted ``list[Path]`` a glob matches.
    """

    path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _checked(self.path))

    @property
    def is_glob(self) -> bool:
        """Whether ``path`` is a pattern, which may match several files."""
        return is_glob(self.path)

    def describe(self, context: Context) -> str:
        return context.shown(self.path)

    def depends_on(self, context: Context) -> tuple[str, ...]:
        return (context.shown(self.path),)

    def observe(self, context: Context) -> Sighting:
        shown = context.shown(self.path)
        if not self.is_glob:
            file = context.file(shown)
            return Sighting(file, (_record(shown, file, context.root),))
        found = files(shown, context.root)
        if not found:
            nothing = Obstacle(f"the glob {shown!r}", "matches no file")
            return Sighting(found, (Observation(shown, shown, obstacle=nothing),))
        return Sighting(found, tuple(_record(shown, file, context.root) for file in found))


@dataclass(frozen=True)
class JsonValue(Observable):
    """A value in a JSON file. The step receives the value.

    ``path`` is relative to the directory of the file that declares the step, and names one
    file. ``pointer`` designates the value in it, as a JSON Pointer (RFC 6901):
    ``"/version"``, ``"/authors/0/name"``; the whole document by default.
    """

    path: str
    pointer: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _checked(self.path, "JsonValue()"))
        if is_glob(self.path):
            raise TypeError(f"JsonValue() takes the path of one file, not the glob {self.path!r}")
        if not isinstance(self.pointer, str) or (self.pointer and self.pointer[0] != "/"):
            raise TypeError(
                f"JsonValue() takes a JSON Pointer, such as '/version', not {self.pointer!r}"
            )

    def describe(self, context: Context) -> str:
        return f"{context.shown(self.path)}#{self.pointer}"

    def depends_on(self, context: Context) -> tuple[str, ...]:
        return (context.shown(self.path),)

    def observe(self, context: Context) -> Sighting:
        declared, shown = self.describe(context), context.shown(self.path)
        seen, content = _read(declared, context.file(shown), context.root)
        if content is None:
            return Sighting(None, (seen,))
        try:
            value = self._designated(json.loads(content))
        except (OSError, ValueError, LookupError) as error:
            problem = Obstacle(declared, _json_problem(error), "Correct the file, or the pointer.")
            return Sighting(None, (Observation(declared, seen.path, obstacle=problem),))
        return Sighting(
            value, (Observation(declared, seen.path, seen.sha256, seen.size, value=value),)
        )

    def _designated(self, document: Any) -> Any:
        value = document
        for token in self.pointer.split("/")[1:]:
            key = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not _INDEX.fullmatch(key):
                    raise LookupError(key)
                value = value[int(key)]
            elif isinstance(value, dict):
                value = value[key]
            else:
                raise LookupError(key)
        return value


def _json_problem(error: Exception) -> str:
    if isinstance(error, LookupError) or type(error) is ValueError:
        return "designates no value in its file"
    return f"cannot be read as JSON: {error}"


@dataclass(frozen=True)
class Env(Observable):
    """An environment variable. The step receives its value, a string.

    A variable that is not set is unreachable. Unless ``display``, it is hidden: the
    report says only that it was observed, neither its value nor its SHA-256, since a
    variable may hold a secret, and a short one is guessed from its SHA-256. A report with
    a hidden variable cannot be checked by ``jpipe-runner status``: only a new run tells
    whether it changed.
    """

    name: str
    display: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip() or "=" in self.name:
            raise TypeError(f"Env() takes the name of an environment variable, not {self.name!r}")

    def describe(self, context: Context) -> str:
        return f"env:{self.name}"

    def observe(self, context: Context) -> Sighting:
        declared = self.describe(context)
        value = os.environ.get(self.name)
        if value is None:
            what = f"the environment variable {self.name!r}"
            unset = Obstacle(
                what, "is not set", "Set it where the runner runs, or stop observing it."
            )
            return Sighting(None, (Observation(declared, obstacle=unset, variable=self.name),))
        if not self.display:
            return Sighting(value, (Observation(declared, variable=self.name, hidden=True),))
        seen = Observation(declared, sha256=fingerprint(value), value=value, variable=self.name)
        return Sighting(value, (seen,))


def _record(declared: str, file: Path, root: Path) -> Observation:
    """The observation of ``file``, read once to hash and measure it."""
    path = file.relative_to(root).as_posix()
    obstacle = _obstacle(file, path)
    if obstacle is None:
        try:
            sha256, size = digest(file)
        except OSError as error:
            obstacle = _unreadable(path, error)
        else:
            return Observation(declared, path, sha256, size)
    return Observation(declared, path, obstacle=obstacle)


def _read(declared: str, file: Path, root: Path) -> tuple[Observation, bytes | None]:
    """The observation of ``file`` and its content, from one read, so that the SHA-256
    recorded is that of the bytes the caller uses. ``None`` when it could not be read."""
    path = file.relative_to(root).as_posix()
    obstacle = _obstacle(file, path)
    if obstacle is None:
        try:
            content = file.read_bytes()
        except OSError as error:
            obstacle = _unreadable(path, error)
        else:
            sha256 = hashlib.sha256(content).hexdigest()
            return Observation(declared, path, sha256, len(content)), content
    return Observation(declared, path, obstacle=obstacle), None


def _unreadable(path: str, error: OSError) -> Obstacle:
    problem = f"cannot be read: {error.strerror or error}"
    return Obstacle(path, problem, "Make it readable by the user the runner runs as.")


def _obstacle(file: Path, path: str) -> Obstacle | None:
    """What keeps ``file``, shown as ``path``, from being read, found without opening it."""
    if file.is_dir():
        fix = f"Observe the files it holds, with a glob such as {path + '/**/*'!r}."
        return Obstacle(path, "is a directory, and evidence observes files", fix)
    if not file.exists():
        return Obstacle(path, "does not exist")
    if not file.is_file():
        # A FIFO, a socket or a device: reading it could block, or never end.
        problem = "is not a regular file, such as a pipe, a socket or a device"
        fix = "Observe a regular file: the runner reads what an evidence observes, to the end."
        return Obstacle(path, problem, fix)
    return None


def _checked(path: object, owner: str = _EVIDENCE) -> str:
    """``path``, checked and in canonical form: it names files relative to the file that
    declares the step, by name or by glob. Errors name ``owner``, what took it."""
    if not isinstance(path, str) or not path.strip():
        example = "observes={'changelog': 'CHANGELOG.md'}"
        if owner != _EVIDENCE:
            example = "JsonValue('package.json', '/version')"
        raise TypeError(f"{owner} takes paths as non-empty strings: {example}")
    if PurePosixPath(path).is_absolute() or PureWindowsPath(path).anchor:
        raise TypeError(
            f"{owner} takes paths relative to the file that declares the "
            f"step, so that the library works on every machine, not {path!r}"
        )
    if path.endswith(("/", "\\")):
        _directory(path, owner)
    if any("**" in part and part != "**" for part in path.replace("\\", "/").split("/")):
        raise TypeError(
            f"{owner}: '**' matches any depth only as a whole part of a "
            f"path, as in 'build/**/*.xml', not {path!r}"
        )
    return _canonical(path, owner)


def _canonical(path: str, owner: str = _EVIDENCE) -> str:
    """``path`` with ``.`` and ``..`` resolved as text before its first wildcard. A leading
    ``..`` is kept. One after a wildcard is refused: what it names depends on the
    directories the glob finds."""
    parts = path.split("/")
    first = next((i for i, part in enumerate(parts) if is_glob(part)), len(parts))
    if ".." in parts[first:]:
        raise TypeError(
            f"{owner} takes '..' only before the first wildcard, as in "
            f"'../shared/*.yml', not {path!r}"
        )
    literal = posixpath.normpath("/".join(parts[:first]) or ".")
    kept = [] if literal == "." else literal.split("/")
    kept += [part for part in parts[first:] if part not in ("", ".")]
    if not kept or kept[-1] == "..":
        _directory(path, owner)
    return "/".join(kept)


def _directory(path: str, owner: str = _EVIDENCE) -> None:
    glob = path.rstrip("/\\") + "/**/*"
    raise TypeError(
        f"{owner} takes files, and {path!r} names a directory. "
        f"Observe the files it holds, with a glob such as {glob!r}."
    )
