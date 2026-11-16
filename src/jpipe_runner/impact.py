"""Impact and staleness: what a change to a file reaches in an argument (ADR-0025, #146).

Both work from a JSON report (ADR-0011), the contract that says, for each element, the
elements it ``supports``, the paths its step declares it ``observes``, and the
``artifacts`` it observed. Neither runs a step:

- ``affected(document, changed)``: the evidence whose declared paths match a changed file,
  and every element above it. The report of a dry run (ADR-0024) is enough.
- ``stale(document, root)``: what a run observed that has changed since, compared with
  the files under ``root`` and the environment now, by SHA-256;
- ``unverified(document)``: what a run observed that the report cannot confirm, because
  it is hidden, or because only the step library can observe it again.

Both are only as good as the declarations: a file a step reads without declaring it is
invisible to them.
"""

import json
import os
import subprocess
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from os import PathLike
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from jpipe_runner.json_report import SCHEMA, SCHEMA_VERSION
from jpipe_runner.observables import (
    designates_one,
    digest,
    files,
    fingerprint,
    is_glob,
    matches,
    readable,
)

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
    """How what was observed, a file or an environment variable, differs from what a run
    recorded."""

    CHANGED = "changed"
    """Its content differs: its SHA-256 is not the one recorded."""
    VANISHED = "vanished"
    """It was read by the run, and is gone."""
    APPEARED = "appeared"
    """It could not be read by the run, and can be now."""
    ADDED = "added"
    """It matches a glob an evidence observes, and the run did not see it."""


@dataclass(frozen=True)
class Change:
    """One thing observed that differs from what a run recorded."""

    element: str
    """The id of the evidence that observes it."""
    path: str
    """The file, relative to the root, as the report shows it; or what was declared, such
    as ``env:CI``."""
    kind: ChangeKind


class Unchecked(StrEnum):
    """Why something a run observed cannot be compared with what it is now."""

    HIDDEN = "hidden"
    """The report holds neither its value nor its SHA-256."""
    UNREADABLE = "library"
    """It is neither a file nor an environment variable: only the step library that
    observed it can observe it again."""


@dataclass(frozen=True)
class Unverified:
    """One thing a run observed that a report alone cannot confirm: it takes a new run."""

    element: str
    """The id of the evidence that observes it."""
    declared: str
    """What was declared, as the report shows it."""
    why: Unchecked


def read(path: str | PathLike[str]) -> dict[str, Any]:
    """The JSON report in the file at ``path``.

    Raises ``OSError`` if the file cannot be read, and ``InvalidReportError`` if it is not
    a report of the schema's major version. A report of another minor version is read: the
    fields a later one adds are ignored, and those an earlier one lacks are optional.
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
    # A report of this version is checked against its schema; one of another minor version
    # only for the fields this version knows.
    validator = _VALIDATOR if version == SCHEMA_VERSION else _LATER_VALIDATOR
    problem = next(iter(validator.iter_errors(document)), None)
    if problem is not None:
        raise InvalidReportError(
            f"{path} is not a JSON report: {problem.json_path}: {problem.message}"
        )
    return dict(document)


def affected(document: Document, changed: Iterable[str]) -> Impact:
    """What the ``changed`` files, relative to the root, reach in the argument the report
    ``document`` describes."""
    files = tuple(sorted(set(changed)))
    elements = document["elements"]
    evidence = [
        element["id"] for element in elements if any(_observes(element, file) for file in files)
    ]
    observed = {file for file in files if any(_observes(element, file) for element in elements)}
    return Impact(
        files,
        tuple(evidence),
        above(document, evidence),
        tuple(file for file in files if file not in observed),
    )


def _observes(element: Mapping[str, Any], file: str) -> bool:
    """Whether one of the paths ``element``'s step declares it observes matches ``file``."""
    return any(matches(file, pattern) for pattern in element["observes"])


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


def stale(
    document: Document, root: Path = Path(), environment: Mapping[str, str] | None = None
) -> tuple[Change, ...]:
    """What the run of ``document`` observed that differs now from what it recorded, in
    report order: the files under ``root``, and the variables of ``environment``, by
    default the process's."""
    variables = os.environ if environment is None else environment
    return tuple(
        change
        for element in document["elements"]
        for change in (*_changes(element, root), *_variables(element, variables))
    )


def unverified(document: Document) -> tuple[Unverified, ...]:
    """What the run of ``document`` observed that cannot be compared with what it is now:
    what the report hides, and what only a step library can observe again. While there is
    any, the report cannot be said to hold."""
    return tuple(
        Unverified(element["id"], observation["declared"], why)
        for element in document["elements"]
        for observation in element.get("observations", ())
        if (why := _unchecked(observation)) is not None
    )


def _unchecked(observation: Mapping[str, Any]) -> Unchecked | None:
    if observation["hidden"]:
        return Unchecked.HIDDEN
    return None if observation["variable"] is not None else Unchecked.UNREADABLE


def _variables(element: Mapping[str, Any], environment: Mapping[str, str]) -> Iterator[Change]:
    """Each environment variable of ``element`` whose value differs from the one recorded."""
    for observation in element.get("observations", ()):
        name = observation["variable"]
        if name is None or observation["hidden"]:
            continue
        if (kind := _variable(observation, environment.get(name))) is not None:
            yield Change(element["id"], observation["declared"], kind)


def _variable(observation: Mapping[str, Any], value: str | None) -> ChangeKind | None:
    """How a variable, now set to ``value`` or unset, differs from what was recorded."""
    if not observation["reachable"]:
        return None if value is None else ChangeKind.APPEARED
    if value is None:
        return ChangeKind.VANISHED
    return None if fingerprint(value) == observation["sha256"] else ChangeKind.CHANGED


def _changes(element: Mapping[str, Any], root: Path) -> Iterator[Change]:
    """Each file of ``element`` that differs, once: a file that several of its declared
    paths designate is recorded under each of them."""
    recorded = {artifact["path"] for artifact in element["artifacts"]}
    # The globs files were recorded under. One a library's observable depends on, without
    # recording files under it, says nothing of the files the run saw. A report of
    # version 1.0 records no `declared`: every glob there is a File's.
    declared = {artifact.get("declared") for artifact in element["artifacts"]}
    found = [
        Change(element["id"], artifact["path"], kind)
        for artifact in element["artifacts"]
        if (kind := _compared(artifact, root)) is not None
    ]
    for pattern in element["observes"]:
        # A path whose only wildcards are escaped, as in app/[[]slug]/a.md, is one file,
        # compared above, unless it was recorded under its pattern, having matched nothing.
        if not element["artifacts"] or (designates_one(pattern) and pattern not in recorded):
            continue
        if None not in declared and pattern not in declared:
            continue
        for file in files(pattern, root):
            shown = file.relative_to(root).as_posix()
            if shown not in recorded:
                found.append(Change(element["id"], shown, ChangeKind.ADDED))
    yield from dict.fromkeys(found)


def sha256_read(artifact: Mapping[str, Any]) -> str | None:
    """The SHA-256 of the file of ``artifact`` as the run read it, or None if it read none.
    A file it read without finding what was observed in it, such as the value a JSON
    Pointer designates, is unreachable, and has one (in ``read``, since 1.1)."""
    if artifact["reachable"]:
        return str(artifact["sha256"])
    read = artifact.get("read")
    return None if read is None else str(read["sha256"])


def _compared(artifact: Mapping[str, Any], root: Path) -> ChangeKind | None:
    """How the file of ``artifact`` differs from what was recorded, if it does. A file the
    run read is compared by its SHA-256: only a file it did not read can have appeared."""
    file = root / artifact["path"]
    recorded = sha256_read(artifact)
    if recorded is None:
        # A glob that matched nothing is recorded under its pattern: what it matches now
        # is found as added.
        return None if _matched_nothing(artifact) or not readable(file) else ChangeKind.APPEARED
    if not file.is_file():
        return ChangeKind.VANISHED
    try:
        sha256, _ = digest(file)
    except OSError:
        return ChangeKind.VANISHED
    return None if sha256 == recorded else ChangeKind.CHANGED


def _matched_nothing(artifact: Mapping[str, Any]) -> bool:
    """Whether ``artifact`` records a glob that matched no file, rather than a file."""
    path = artifact["path"]
    # A report of version 1.0 does not say what a file was declared as: its path is all
    # there is to go by, and a file whose name holds a wildcard is taken for a glob.
    return is_glob(path) and artifact.get("declared", path) == path


def changed_since(ref: str, root: Path = Path()) -> list[str]:
    """The files under ``root`` that differ from the git revision ``ref``, and those git
    does not track yet (but does not ignore), relative to ``root``, sorted.

    Raises ``FileNotFoundError`` if git is not installed, and ``OSError`` if it fails: the
    directory is not in a repository, or ``ref`` is not a revision.
    """
    if ref.startswith("-"):
        raise ValueError(f"{ref!r} is not a git revision")
    # -z: each path as it is, NUL-terminated, rather than quoted when it is not ASCII.
    # --no-renames: a renamed file is listed under both names, so that the evidence that
    # observed the old one is affected.
    diff = _git(["diff", "--name-only", "--no-renames", "-z", "--relative", ref, "--"], root)
    untracked = _git(["ls-files", "-z", "--others", "--exclude-standard"], root)
    return sorted({*diff, *untracked})


def _git(arguments: list[str], root: Path) -> list[str]:
    try:
        done = subprocess.run(["git", *arguments], cwd=root, capture_output=True, check=False)
    except FileNotFoundError:
        raise FileNotFoundError("git is not installed, or not on the PATH") from None
    if done.returncode != 0:
        errors = done.stderr.decode("utf-8", "replace").strip().splitlines()
        problem = next(iter(errors), f"exit code {done.returncode}")
        raise OSError(f"git {arguments[0]} failed: {problem}")
    # Paths are bytes, in whatever encoding the file system holds: decoded as Python
    # decodes file names, so that one that is not UTF-8 is still listed, and found.
    return [os.fsdecode(path) for path in done.stdout.split(b"\0") if path]


def render_impact(document: Document, impact: Impact) -> str:
    """``impact`` as text, for people: each changed file and what observes it, then the
    elements it reaches."""
    observers = {
        file: [element["id"] for element in document["elements"] if _observes(element, file)]
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
        lines.append(f"  {_printable(file):<{width}}  {by}")
    lines.append("")
    if not impact.affected:
        lines.append("Nothing is affected: no evidence observes these files.")
    else:
        lines.append(f"Affected ({len(impact.affected)} elements):")
        lines.extend(_elements(document, impact.affected))
    return "\n".join(lines) + "\n"


def render_stale(
    document: Document, changes: Sequence[Change], unchecked: Sequence[Unverified] = ()
) -> str:
    """``changes`` and ``unchecked`` as text, for people: what changed, and the elements
    above the evidence that observes it; then what could not be checked, and the elements
    that only a new run confirms."""
    lines = list(_header(document))
    if not changes and not unchecked:
        lines.append("Everything the run observed is as it was: its report still holds.")
        return "\n".join(lines) + "\n"
    if changes:
        kinds = max(len(change.kind) for change in changes)
        paths = max(len(change.path) for change in changes)
        lines.append("Changed since the run:")
        for change in changes:
            lines.append(f"  {change.kind:<{kinds}}  {change.path:<{paths}}  {change.element}")
        lines.append("")
        stale_ids = above(document, (change.element for change in changes))
        lines.append(f"Stale ({len(stale_ids)} elements):")
        lines.extend(_elements(document, stale_ids))
    if unchecked:
        if changes:
            lines.append("")
        lines.extend(_rerun(document, unchecked))
    return "\n".join(lines) + "\n"


_RERUN = {
    Unchecked.HIDDEN: "Information was hidden from the report, so it needs a new run:",
    Unchecked.UNREADABLE: "Only its step library can observe it again, so it needs a new run:",
}


def _rerun(document: Document, unchecked: Sequence[Unverified]) -> Iterator[str]:
    """What could not be checked, by reason, then the elements a new run must judge."""
    width = max(len(item.declared) for item in unchecked)
    for why, title in _RERUN.items():
        items = [item for item in unchecked if item.why is why]
        if items:
            yield title
            for item in items:
                yield f"  {item.declared:<{width}}  {item.element}"
            yield ""
    ids = above(document, (item.element for item in unchecked))
    yield f"Not confirmed ({len(ids)} elements):"
    yield from _elements(document, ids)


def _printable(path: str) -> str:
    """``path`` as text that any output can write: a byte of a file name that is not
    UTF-8 is shown escaped."""
    return os.fsencode(path).decode("utf-8", "backslashreplace")


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
