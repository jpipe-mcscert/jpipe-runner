"""Artifacts: what an evidence observes, checked and recorded just before its step is called.

An evidence declares the artifacts it observes (ADR-0018): a file, or a glob of files,
relative to the run's root. Before calling its step, the runner observes each one
(ADR-0019), in three steps that can be taken apart (ADR-0027):

- **located** (``locate``): the file a path names, or the files a glob matches, none read;
- **recorded** (``record``): each file's path relative to the root, its SHA-256 and its
  size, as the step is about to see it, or the ``Obstacle`` that keeps it from being read;
- **injected** (``Located.argument``): the step receives a ``Path``, or the sorted
  ``list[Path]`` a glob matches.

An artifact that cannot be reached, a missing or unreadable file, a directory or anything
else that is not a regular file, or a glob that matches nothing, is reported with
``JP019`` (``unreachable``), and the step is not called: an observed artifact is never
optional.

What a glob designates is defined here, and nowhere else: ``files`` lists the files it
matches under a root, and ``matches`` says whether it would match a path, without the file
system. A property test holds them to the same answer.
"""

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.steps import Artifact

UNREACHABLE_ARTIFACT = "JP019"

_CHUNK = 1 << 16
_RECURSIVE = "**"

_MISSING_FIX = (
    "Make sure the artifact exists when the runner runs, at this path relative to the "
    "directory it runs in, or correct the path in observes={...}."
)


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


@dataclass(frozen=True)
class Obstacle:
    """Why an artifact could not be reached."""

    what: str
    """What could not be reached: the file's path, or the glob that matched nothing."""
    problem: str
    fix: str = _MISSING_FIX


@dataclass(frozen=True)
class Located:
    """An artifact located under a root: the files it designates, none of them read."""

    artifact: Artifact
    files: tuple[Path, ...]
    """The file a path names, whether or not it exists; the files a glob matches, sorted,
    which may be none."""

    @property
    def argument(self) -> Path | list[Path]:
        """What the step receives: a ``Path``, or the ``list[Path]`` of a glob."""
        return list(self.files) if self.artifact.is_glob else self.files[0]


@dataclass(frozen=True)
class Observation:
    """A file an evidence observed, as it was just before its step was called.

    ``path`` is relative to the run's root, in POSIX form: the declared path, or for a
    glob the file it matched. ``sha256`` and ``size`` are ``None`` when the file could not
    be reached, and ``obstacle`` says why; a glob that matches nothing is recorded once,
    under its pattern.
    """

    artifact: Artifact
    """The artifact as the evidence declares it: the parameter it is passed to, and its path."""
    path: str
    sha256: str | None = None
    size: int | None = None
    obstacle: Obstacle | None = None

    @property
    def reachable(self) -> bool:
        return self.sha256 is not None


@dataclass(frozen=True)
class Observed:
    """The artifacts of one evidence, observed: what was recorded, what to pass to the step,
    and a ``JP019`` diagnostic for each artifact that could not be reached."""

    observations: tuple[Observation, ...]
    arguments: Mapping[str, Path | list[Path]]
    """What the step receives, by parameter name. Complete only when ``reachable``."""
    diagnostics: tuple[Diagnostic, ...]

    @property
    def reachable(self) -> bool:
        """Whether every artifact was reached, so that the step can be called."""
        return not self.diagnostics


def observe(artifacts: Iterable[Artifact], root: Path, element: str) -> Observed:
    """Observe ``artifacts``, declared by the evidence bound to ``element``, under ``root``:
    locate each one, record its files, and say what to pass to the step."""
    located = [locate(artifact, root) for artifact in artifacts]
    observations = tuple(o for found in located for o in record(found, root))
    arguments = {found.artifact.name: found.argument for found in located}
    return Observed(observations, MappingProxyType(arguments), unreachable(observations, element))


def locate(artifact: Artifact, root: Path) -> Located:
    """The files ``artifact`` designates under ``root``. Nothing is read."""
    if artifact.is_glob:
        return Located(artifact, tuple(files(artifact.path, root)))
    return Located(artifact, (root / artifact.path,))


def record(located: Located, root: Path) -> tuple[Observation, ...]:
    """An observation of each file of ``located``, read once to hash and measure it; or,
    for a glob that matched nothing, one observation of its pattern."""
    artifact = located.artifact
    if not located.files:
        nothing = Obstacle(f"the glob {artifact.path!r}", "matches no file")
        return (Observation(artifact, artifact.path, obstacle=nothing),)
    return tuple(_record(artifact, file, root) for file in located.files)


def unreachable(observations: Iterable[Observation], element: str) -> tuple[Diagnostic, ...]:
    """A ``JP019`` diagnostic, about ``element``, for each of ``observations`` that could
    not be reached."""
    return tuple(
        Diagnostic(
            UNREACHABLE_ARTIFACT,
            Severity.ERROR,
            f"{o.obstacle.what}, observed as {o.artifact.name!r}, {o.obstacle.problem}",
            element=element,
            fix=o.obstacle.fix,
        )
        for o in observations
        if o.obstacle is not None
    )


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


def _record(artifact: Artifact, file: Path, root: Path) -> Observation:
    path = file.relative_to(root).as_posix()
    obstacle = _obstacle(file, path)
    if obstacle is None:
        try:
            sha256, size = digest(file)
        except OSError as error:
            problem = f"cannot be read: {error.strerror or error}"
            obstacle = Obstacle(path, problem, "Make it readable by the user the runner runs as.")
        else:
            return Observation(artifact, path, sha256, size)
    return Observation(artifact, path, obstacle=obstacle)


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


def digest(file: Path) -> tuple[str, int]:
    """The SHA-256 of ``file``'s content, and its size in bytes, from one read."""
    hashed = hashlib.sha256()
    size = 0
    with file.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            hashed.update(chunk)
            size += len(chunk)
    return hashed.hexdigest(), size
