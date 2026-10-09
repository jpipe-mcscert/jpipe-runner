"""The JSON report: the machine-readable contract of a run (ADR-0011).

``document(report)`` is the report as a JSON document, which ``report.schema.json``, shipped
in the package, describes; ``dumps(report)`` is its text. The document is versioned by
``schema_version``: within a major version, a minor version only adds optional fields, so
a consumer ignores the fields it does not know.

It is deterministic: two runs over the same files give the same document. It holds no
time, duration or host name, paths are relative to where the runner runs, and keys come
in a fixed order. A produced value that is not JSON (a ``Path``, a ``datetime``, an object,
a float that is not finite) is written as its ``repr`` and its type, never refused. That
``repr`` is made canonical: a path under the run's root is shown relative to it, the
items of a set are sorted, and an object's address is left out, at any depth.
"""

import json
import math
import re
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

from jpipe_runner.artifacts import Observation
from jpipe_runner.diagnostics import Diagnostic, shown_path
from jpipe_runner.report import ElementReport, RunReport, Trace

SCHEMA_VERSION = "1.0"

SCHEMA: dict[str, Any] = json.loads(
    files("jpipe_runner").joinpath("schema/report.schema.json").read_text(encoding="utf-8")
)

_REPR_LIMIT = 1000
"""The longest ``repr`` written for a value that is not JSON, in characters."""

_ADDRESS = re.compile(r" at 0x[0-9A-Fa-f]+")
"""The address in an object's default repr, ``<steps.Report object at 0x10f3a2b50>``."""

_RECURSION: dict[type, str] = {
    list: "[...]",
    dict: "{...}",
    tuple: "(...)",
    set: "{...}",
    frozenset: "{...}",
}


def document(report: RunReport) -> dict[str, Any]:
    """``report`` as a JSON document, as ``report.schema.json`` describes it."""
    summary = report.summary
    return {
        "schema_version": SCHEMA_VERSION,
        "justification": report.justification,
        "verdict": str(report.verdict),
        "strict": report.strict,
        "summary": {
            "elements": summary.elements,
            "pass": summary.passed,
            "fail": summary.failed,
            "skip": summary.skipped,
            "not_run": summary.not_run,
            "errors": summary.errors,
            "warnings": summary.warnings,
        },
        "elements": [_element(element, report.root) for element in report.elements],
        "diagnostics": [_diagnostic(report, diagnostic) for diagnostic in report.diagnostics],
        "diagram": report.diagram,
        "dataflow": report.dataflow,
    }


def dumps(report: RunReport) -> str:
    """The text of ``report``'s JSON document: indented by two spaces, in UTF-8, with a
    final newline."""
    return json.dumps(document(report), indent=2, ensure_ascii=False) + "\n"


def _element(element: ElementReport, root: Path) -> dict[str, Any]:
    return {
        "id": element.id,
        "label": element.label,
        "kind": str(element.kind),
        "aliases": list(element.aliases),
        "supports": list(element.supports),
        "status": None if element.status is None else str(element.status),
        "reason": element.reason,
        "blocked_by": list(element.blocked_by),
        "ran": element.ran,
        "bound_to": element.step,
        "bound_by": list(element.designators),
        "observes": list(element.observes),
        "consumes": list(element.consumes),
        "produces": list(element.produces),
        "produced": {name: encoded(value, root) for name, value in element.produced.items()},
        "artifacts": [_artifact(artifact) for artifact in element.artifacts],
    }


def _artifact(artifact: Observation) -> dict[str, Any]:
    return {
        "path": artifact.path,
        "reachable": artifact.reachable,
        "sha256": artifact.sha256,
        "size": artifact.size,
    }


def _diagnostic(report: RunReport, diagnostic: Diagnostic) -> dict[str, Any]:
    trace = report.trace(diagnostic)
    return {
        "code": diagnostic.code,
        "severity": str(diagnostic.severity),
        "element": diagnostic.element,
        "message": diagnostic.message,
        "fix": diagnostic.fix,
        "traceback": None if trace is None else _trace(trace),
    }


def _trace(trace: Trace) -> dict[str, Any]:
    return {
        "exception": trace.exception,
        "message": trace.message,
        "frames": [
            {"file": f.file, "line": f.line, "function": f.function, "code": f.code}
            for f in trace.frames
        ],
        "cause": None if trace.cause is None else _trace(trace.cause),
    }


def encoded(value: Any, root: Path = Path()) -> dict[str, Any]:
    """A produced value, as the report writes it: ``{"value": ...}`` if it is JSON, and
    ``{"repr": ..., "type": ...}`` otherwise, with a canonical ``repr`` (paths shown
    relative to ``root``)."""
    if _is_json(value, set()):
        return {"value": _plain(value)}
    return {"repr": _cut(_Canonical(root)(value)), "type": _type_name(type(value))}


def _is_json(value: Any, seen: set[int]) -> bool:
    """Whether ``value`` is JSON as it is: ``None``, a ``bool``, an ``int``, a finite
    ``float``, a ``str``, or a list, tuple or mapping with ``str`` keys of such values."""
    if value is None or isinstance(value, bool | int | str):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if not isinstance(value, list | tuple | Mapping) or id(value) in seen:
        return False
    seen = seen | {id(value)}
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json(v, seen) for key, v in value.items())
    return all(_is_json(item, seen) for item in value)


def _plain(value: Any) -> Any:
    """``value``, which is JSON, with its containers as lists and dicts."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


class _Canonical:
    """The ``repr`` of a value, the same on every run: Python's own, except that a path
    under the root is shown relative to it, the items of a set are sorted, and an object's
    address is left out, in the value and in the lists, tuples, sets and dicts it holds."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._seen: set[int] = set()

    def __call__(self, value: Any) -> str:
        kind = type(value)
        if isinstance(value, Path):
            return repr(kind(shown_path(str(value), self._root)))
        if kind not in _RECURSION:
            return _ADDRESS.sub("", _repr(value))
        if id(value) in self._seen:
            return _RECURSION[kind]
        self._seen.add(id(value))
        try:
            return self._container(value)
        finally:
            self._seen.discard(id(value))

    def _container(self, value: Any) -> str:
        if isinstance(value, dict):
            return "{" + ", ".join(f"{self(k)}: {self(v)}" for k, v in value.items()) + "}"
        items = [self(item) for item in value]
        if isinstance(value, list):
            return "[" + ", ".join(items) + "]"
        if isinstance(value, tuple):
            return "(" + ", ".join(items) + ("," if len(items) == 1 else "") + ")"
        name = type(value).__name__
        if not items:
            return f"{name}()"
        body = "{" + ", ".join(sorted(items)) + "}"
        return body if name == "set" else f"{name}({body})"


def _repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception as error:  # a broken __repr__ must not break the report
        return f"<{_type_name(type(value))} object: repr() raised {type(error).__name__}>"


def _cut(text: str) -> str:
    if len(text) > _REPR_LIMIT:
        return text[: _REPR_LIMIT - 1] + "…"
    return text


def _type_name(kind: type) -> str:
    if kind.__module__ == "builtins":
        return kind.__qualname__
    return f"{kind.__module__}.{kind.__qualname__}"
