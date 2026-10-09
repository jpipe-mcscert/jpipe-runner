"""Artifacts: what an evidence observes, checked and recorded just before its step is called.

An evidence declares the artifacts it observes (ADR-0018): a file, or a glob of files,
relative to the run's root. Before calling its step, the runner observes each one
(ADR-0019):

- **reached**: a file that exists and can be read, or every file a glob matches, when it
  matches at least one;
- **recorded**: each file's path relative to the root, its SHA-256 and its size, as the
  step is about to see it;
- **injected**: the step receives a ``Path``, or the sorted ``list[Path]`` a glob matches.

An artifact that cannot be reached, a missing or unreadable file, a directory or anything
else that is not a regular file, or a glob that matches nothing, is reported with ``JP019``, and the step is not called: an observed
artifact is never optional.
"""

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.steps import Artifact

UNREACHABLE_ARTIFACT = "JP019"

_CHUNK = 1 << 16

_MISSING_FIX = (
    "Make sure the artifact exists when the runner runs, at this path relative to the "
    "directory it runs in, or correct the path in observes={...}."
)


@dataclass(frozen=True)
class Observation:
    """A file an evidence observed, as it was just before its step was called.

    ``path`` is relative to the run's root, in POSIX form: the declared path, or for a
    glob the file it matched. ``sha256`` and ``size`` are ``None`` when the file could not
    be reached; a glob that matches nothing is recorded once, under its pattern.
    """

    artifact: Artifact
    """The artifact as the evidence declares it: the parameter it is passed to, and its path."""
    path: str
    sha256: str | None = None
    size: int | None = None

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
    """Observe ``artifacts``, declared by the evidence bound to ``element``, under ``root``."""
    observations: list[Observation] = []
    arguments: dict[str, Path | list[Path]] = {}
    diagnostics: list[Diagnostic] = []
    for artifact in artifacts:
        if artifact.is_glob:
            files = sorted(path for path in root.glob(artifact.path) if path.is_file())
            arguments[artifact.name] = files
            if not files:
                observations.append(Observation(artifact, artifact.path))
                diagnostics.append(
                    _unreachable(
                        element, artifact, f"the glob {artifact.path!r}", "matches no file"
                    )
                )
        else:
            files = [root / artifact.path]
            arguments[artifact.name] = files[0]
        for file in files:
            observation, diagnostic = _record(artifact, file, root, element)
            observations.append(observation)
            if diagnostic is not None:
                diagnostics.append(diagnostic)
    return Observed(tuple(observations), MappingProxyType(arguments), tuple(diagnostics))


def _record(
    artifact: Artifact, file: Path, root: Path, element: str
) -> tuple[Observation, Diagnostic | None]:
    """The observation of ``file``, and the diagnostic saying why it is unreachable, if it is."""
    path = file.relative_to(root).as_posix()
    if file.is_dir():
        problem = "is a directory, and evidence observes files"
        fix = f"Observe the files it holds, with a glob such as {path + '/**/*'!r}."
        return Observation(artifact, path), _unreachable(element, artifact, path, problem, fix)
    if not file.exists():
        return Observation(artifact, path), _unreachable(element, artifact, path, "does not exist")
    if not file.is_file():
        # A FIFO, a socket or a device: reading it could block, or never end.
        problem = "is not a regular file, such as a pipe, a socket or a device"
        fix = "Observe a regular file: the runner reads what an evidence observes, to the end."
        return Observation(artifact, path), _unreachable(element, artifact, path, problem, fix)
    try:
        sha256, size = _digest(file)
    except OSError as error:
        problem = f"cannot be read: {error.strerror or error}"
        fix = "Make it readable by the user the runner runs as."
        return Observation(artifact, path), _unreachable(element, artifact, path, problem, fix)
    return Observation(artifact, path, sha256, size), None


def _digest(file: Path) -> tuple[str, int]:
    """The SHA-256 of ``file``'s content, and its size in bytes, from one read."""
    digest = hashlib.sha256()
    size = 0
    with file.open("rb") as stream:
        while chunk := stream.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _unreachable(
    element: str, artifact: Artifact, what: str, problem: str, fix: str = _MISSING_FIX
) -> Diagnostic:
    return Diagnostic(
        UNREACHABLE_ARTIFACT,
        Severity.ERROR,
        f"{what}, observed as {artifact.name!r}, {problem}",
        element=element,
        fix=fix,
    )
