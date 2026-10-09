"""Impact and staleness: what a change to a file reaches in an argument (ADR-0025, #146).

Both work from a JSON report (ADR-0011), the contract that says, for each element, the
elements it ``supports``, the paths its step declares it ``observes``, and the
``artifacts`` it observed. Neither runs a step:

- ``affected(document, changed)``: the evidence whose declared paths match a changed file,
  and every element above it. The report of a dry run (ADR-0024) is enough.
- ``stale(document, root)``: the files a run observed that have changed since, compared
  with the files under ``root`` now, by their SHA-256.

Both are only as good as the declarations: a file a step reads without declaring it is
invisible to them.
"""

import json
import subprocess
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from fnmatch import fnmatchcase
from os import PathLike
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator

from jpipe_runner.artifacts import digest
from jpipe_runner.json_report import SCHEMA, SCHEMA_VERSION
from jpipe_runner.steps import is_glob

Document = Mapping[str, Any]

_MAJOR = SCHEMA_VERSION.partition(".")[0]


def _compatible(schema: Any) -> Any:
    """``schema`` without ``additionalProperties: false``: a later minor version may add
    fields, which a reader ignores (ADR-0011)."""
    if isinstance(schema, dict):
        return {
            key: _compatible(value)
            for key, value in schema.items()
            if not (key == "additionalProperties" and value is False)
        }
    if isinstance(schema, list):
        return [_compatible(value) for value in schema]
    return schema


_VALIDATOR = Draft202012Validator(SCHEMA)
_LATER = _compatible(SCHEMA)
_LATER["properties"]["schema_version"] = {"type": "string", "pattern": f"^{_MAJOR}\\.[0-9]+$"}
_LATER_VALIDATOR = Draft202012Validator(_LATER)
_RECURSIVE = "**"


class InvalidReportError(ValueError):
    """A file that is not a JSON report this version of the runner can read."""


@dataclass(frozen=True)
class Impact:
    """What a set of changed files reaches in an argument."""

    changed: tuple[str, ...]
    """The changed files, relative to the root, sorted."""
    evidence: tuple[str, ...]
    """The evidence whose declared paths match a changed file, in report order."""
    affected: tuple[str, ...]
    """That evidence and every element above it, in report order."""
    unobserved: tuple[str, ...]
    """The changed files that no evidence observes."""


class ChangeKind(StrEnum):
    """How an observed file differs from what a run recorded."""

    CHANGED = "changed"
    """Its content differs: its SHA-256 is not the one recorded."""
    VANISHED = "vanished"
    """It was read by the run, and is gone."""
    APPEARED = "appeared"
    """It could not be read by the run, and is there now."""
    ADDED = "added"
    """It matches a glob an evidence observes, and the run did not see it."""


@dataclass(frozen=True)
class Change:
    """One observed file that differs from what a run recorded."""

    element: str
    """The id of the evidence that observes it."""
    path: str
    """The file, relative to the root, as the report shows it."""
    kind: ChangeKind


def read(path: str | PathLike[str]) -> dict[str, Any]:
    """The JSON report in the file at ``path``.

    Raises ``OSError`` if the file cannot be read, and ``InvalidReportError`` if it is not
    a report of the schema's major version. A report of a later minor version is read: the
    fields it adds are ignored.
    """
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidReportError(f"{path} is not a JSON report: {error}") from None
    version = document.get("schema_version") if isinstance(document, dict) else None
    if not isinstance(version, str) or version.partition(".")[0] != _MAJOR:
        raise InvalidReportError(
            f"{path} is not a JSON report of version {_MAJOR}.x: its schema_version is {version!r}"
        )
    # A report of this version is checked against its schema; one of a later minor version
    # only for the fields this version knows.
    validator = _VALIDATOR if version == SCHEMA_VERSION else _LATER_VALIDATOR
    problem = next(iter(validator.iter_errors(document)), None)
    if problem is not None:
        raise InvalidReportError(
            f"{path} is not a JSON report: {problem.json_path}: {problem.message}"
        )
    return dict(document)


def matches(path: str, pattern: str) -> bool:
    """Whether the file at ``path`` is one that ``pattern`` designates, both relative to
    the root, as ``Path.glob`` matches them: each segment as ``fnmatch`` does, and ``**``
    for any number of segments, none included."""
    return _matches(PurePosixPath(path).parts, PurePosixPath(pattern).parts)


def _matches(parts: Sequence[str], pattern: Sequence[str]) -> bool:
    if not pattern:
        return not parts
    head, rest = pattern[0], pattern[1:]
    if head == _RECURSIVE:
        return any(_matches(parts[skipped:], rest) for skipped in range(len(parts) + 1))
    return bool(parts) and fnmatchcase(parts[0], head) and _matches(parts[1:], rest)


def affected(document: Document, changed: Iterable[str]) -> Impact:
    """What the ``changed`` files, relative to the root, reach in the argument the report
    ``document`` describes."""
    files = tuple(sorted(set(changed)))
    elements = document["elements"]
    evidence = [
        element["id"]
        for element in elements
        if any(matches(file, pattern) for file in files for pattern in element["observes"])
    ]
    observed = {
        file
        for file in files
        if any(matches(file, pattern) for element in elements for pattern in element["observes"])
    }
    return Impact(
        files,
        tuple(evidence),
        above(document, evidence),
        tuple(file for file in files if file not in observed),
    )


def above(document: Document, ids: Iterable[str]) -> tuple[str, ...]:
    """The elements ``ids`` and every element they support, directly or not, in the
    order of the report: each after the elements that support it."""
    supports = {element["id"]: element["supports"] for element in document["elements"]}
    reached: set[str] = set()
    pending = list(ids)
    while pending:
        current = pending.pop()
        if current not in reached:
            reached.add(current)
            pending.extend(supports.get(current, ()))
    return tuple(element["id"] for element in document["elements"] if element["id"] in reached)


def stale(document: Document, root: Path = Path()) -> tuple[Change, ...]:
    """The files the run of ``document`` observed that differ now, under ``root``, from
    what it recorded, in report order."""
    return tuple(change for element in document["elements"] for change in _changes(element, root))


def _changes(element: Mapping[str, Any], root: Path) -> Iterator[Change]:
    recorded = {artifact["path"] for artifact in element["artifacts"]}
    for artifact in element["artifacts"]:
        kind = _compared(artifact, root)
        if kind is not None:
            yield Change(element["id"], artifact["path"], kind)
    for pattern in element["observes"]:
        if not is_glob(pattern) or not element["artifacts"]:
            continue
        for file in sorted(path for path in root.glob(pattern) if path.is_file()):
            shown = file.relative_to(root).as_posix()
            if shown not in recorded:
                yield Change(element["id"], shown, ChangeKind.ADDED)


def _compared(artifact: Mapping[str, Any], root: Path) -> ChangeKind | None:
    """How the file of ``artifact`` differs from what was recorded, if it does."""
    file = root / artifact["path"]
    if not artifact["reachable"]:
        # A glob that matched nothing is recorded under its pattern: what it matches now
        # is found as added.
        appeared = not is_glob(artifact["path"]) and file.is_file()
        return ChangeKind.APPEARED if appeared else None
    if not file.is_file():
        return ChangeKind.VANISHED
    try:
        sha256, _ = digest(file)
    except OSError:
        return ChangeKind.VANISHED
    return None if sha256 == artifact["sha256"] else ChangeKind.CHANGED


def changed_since(ref: str, root: Path = Path()) -> list[str]:
    """The files under ``root`` that differ from the git revision ``ref``, and those git
    does not track yet (but does not ignore), relative to ``root``, sorted.

    Raises ``FileNotFoundError`` if git is not installed, and ``OSError`` if it fails: the
    directory is not in a repository, or ``ref`` is not a revision.
    """
    if ref.startswith("-"):
        raise ValueError(f"{ref!r} is not a git revision")
    # -z: each path as it is, NUL-terminated, rather than quoted when it is not ASCII.
    diff = _git(["diff", "--name-only", "-z", "--relative", ref, "--"], root)
    untracked = _git(["ls-files", "-z", "--others", "--exclude-standard"], root)
    return sorted({*diff, *untracked})


def _git(arguments: list[str], root: Path) -> list[str]:
    try:
        done = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        raise FileNotFoundError("git is not installed, or not on the PATH") from None
    if done.returncode != 0:
        problem = next(iter(done.stderr.strip().splitlines()), f"exit code {done.returncode}")
        raise OSError(f"git {arguments[0]} failed: {problem}")
    return [path for path in done.stdout.split("\0") if path]


def render_impact(document: Document, impact: Impact) -> str:
    """``impact`` as text, for people: each changed file and what observes it, then the
    elements it reaches."""
    observers = {
        file: [
            element["id"]
            for element in document["elements"]
            if any(matches(file, pattern) for pattern in element["observes"])
        ]
        for file in impact.changed
    }
    lines = list(_header(document))
    if not impact.changed:
        lines.append("No file changed: nothing is affected.")
        return "\n".join(lines) + "\n"
    width = max(len(file) for file in impact.changed)
    lines.append("Changed files, and the evidence that observes them:")
    for file in impact.changed:
        by = ", ".join(observers[file]) or "(no evidence)"
        lines.append(f"  {file:<{width}}  {by}")
    lines.append("")
    if not impact.affected:
        lines.append("Nothing is affected: no evidence observes these files.")
    else:
        lines.append(f"Affected ({len(impact.affected)} elements):")
        lines.extend(_elements(document, impact.affected))
    return "\n".join(lines) + "\n"


def render_stale(document: Document, changes: Sequence[Change]) -> str:
    """``changes`` as text, for people: each file that changed, then the elements above
    the evidence that observes it."""
    lines = list(_header(document))
    if not changes:
        lines.append("Every file the run observed is as it was: its report still holds.")
        return "\n".join(lines) + "\n"
    kinds = max(len(change.kind) for change in changes)
    paths = max(len(change.path) for change in changes)
    lines.append("Changed since the run:")
    for change in changes:
        lines.append(f"  {change.kind:<{kinds}}  {change.path:<{paths}}  {change.element}")
    lines.append("")
    stale_ids = above(document, (change.element for change in changes))
    lines.append(f"Stale ({len(stale_ids)} elements):")
    lines.extend(_elements(document, stale_ids))
    return "\n".join(lines) + "\n"


def _header(document: Document) -> Iterator[str]:
    yield f"Justification: {document['justification']}"
    yield ""


def _elements(document: Document, ids: Sequence[str]) -> Iterator[str]:
    """One line per element of ``ids``: its kind, its label and its id, aligned."""
    shown = [element for element in document["elements"] if element["id"] in ids]
    kinds = max(len(element["kind"]) for element in shown)
    labels = max(len(element["label"]) for element in shown)
    for element in shown:
        kind = element["kind"].capitalize()
        yield f"  {kind:<{kinds}}  {element['label']:<{labels}}  # {element['id']}"
