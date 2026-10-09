"""Load a justification model from the JSON the jPipe compiler emits (ADR-0001).

A model that cannot be run is never loaded as an empty one. Every problem found becomes a
diagnostic, and they are raised together in an ``InvalidJustificationError``: JP001 when
the text is not JSON or does not match ``justification.schema.json``, then JP002 and JP003
from the model itself (see ``Justification``). v3 logged the failure and ran an empty
graph, which executed nothing and reported success.
"""

import json
from dataclasses import replace
from importlib.resources import files
from os import PathLike
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.model import Element, InvalidJustificationError, Justification, Kind, Relation

SCHEMA_CONFORMANCE = "JP001"

SCHEMA: dict[str, Any] = json.loads(
    files("jpipe_runner").joinpath("schema/justification.schema.json").read_text(encoding="utf-8")
)
_VALIDATOR = Draft202012Validator(SCHEMA)

_SOURCE_FILE = (
    "This is a jPipe source file: compile it with `jpipe process -f JSON`, "
    "and pass the JSON file the compiler writes."
)

_NOT_RUNNABLE = (
    "Templates have abstract supports and cannot be run. "
    "Run a justification that implements the template instead."
)


def load(path: str | PathLike[str]) -> Justification:
    """Load the model in the file at ``path``.

    Raises ``OSError`` if the file cannot be read, and ``InvalidJustificationError`` if
    what it holds is not a model that can be run. A ``.jd`` file is the jPipe source of a
    model, not the JSON the compiler writes from it, and its diagnostic says so.
    """
    try:
        return loads(_read(path))
    except InvalidJustificationError as error:
        if Path(path).suffix != ".jd":
            raise
        raise InvalidJustificationError(
            [replace(d, fix=_SOURCE_FILE) for d in error.diagnostics]
        ) from None


def _read(path: str | PathLike[str]) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise InvalidJustificationError(
            [_nonconformance(f"not UTF-8 text: {error.reason} at byte {error.start}")]
        ) from None


def loads(text: str) -> Justification:
    """Load the model in ``text``. Raises ``InvalidJustificationError`` as ``load`` does."""
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise InvalidJustificationError(
            [_nonconformance(f"not JSON: {error.msg} (line {error.lineno}, column {error.colno})")]
        ) from None

    problems = [_from_schema_error(error, document) for error in _VALIDATOR.iter_errors(document)]
    if problems:
        raise InvalidJustificationError(problems)

    elements = (
        Element(
            id=element["id"],
            label=element["label"],
            kind=Kind(element["type"]),
            aliases=tuple(element.get("aliases", ())),
        )
        for element in document["elements"]
    )
    relations = (Relation(r["source"], r["target"]) for r in document["relations"])
    return Justification(document["name"], elements, relations)


def _nonconformance(message: str, element: str | None = None, fix: str | None = None) -> Diagnostic:
    return Diagnostic(SCHEMA_CONFORMANCE, Severity.ERROR, message, element=element, fix=fix)


def _from_schema_error(error: ValidationError, document: Any) -> Diagnostic:
    path = tuple(error.absolute_path)
    element = None
    if path[:1] == ("elements",) and len(path) > 1:
        candidate = document["elements"][path[1]]
        if isinstance(candidate, dict) and isinstance(candidate.get("id"), str):
            element = candidate["id"]

    not_runnable = (path == ("type",) and error.instance == "template") or (
        path[:1] == ("elements",) and path[2:] == ("type",) and error.instance == "abstract-support"
    )
    return _nonconformance(
        f"{error.json_path}: {error.message}",
        element=element,
        fix=_NOT_RUNNABLE if not_runnable else None,
    )
