"""The JSON report: the machine-readable contract of a run (ADR-0011).

``document(report)`` is the report as a JSON document, which ``report.schema.json``, shipped
in the package, describes; ``dumps(report)`` is its text. The document is versioned by
``schema_version``: within a major version, a minor version only adds optional fields, so
a consumer ignores the fields it does not know.

It is deterministic: two runs over the same files give the same document. It holds no
time, duration or host name, paths are relative to where the runner runs, and keys come
in a fixed order. A produced value that is not JSON (a ``Path``, a ``datetime``, an object,
a float that is not finite) is written as its ``repr`` and its type, never refused.
"""

import json
import math
from collections.abc import Mapping
from importlib.resources import files
from typing import Any

from jpipe_runner.artifacts import Observation
from jpipe_runner.diagnostics import Diagnostic
from jpipe_runner.report import ElementReport, RunReport, Trace

SCHEMA_VERSION = "1.0"

SCHEMA: dict[str, Any] = json.loads(
    files("jpipe_runner").joinpath("schema/report.schema.json").read_text(encoding="utf-8")
)

_REPR_LIMIT = 1000
"""The longest ``repr`` written for a value that is not JSON, in characters."""


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
        "elements": [_element(element) for element in report.elements],
        "diagnostics": [_diagnostic(report, diagnostic) for diagnostic in report.diagnostics],
        "diagram": report.diagram,
    }


def dumps(report: RunReport) -> str:
    """The text of ``report``'s JSON document: indented by two spaces, in UTF-8, with a
    final newline."""
    return json.dumps(document(report), indent=2, ensure_ascii=False) + "\n"


def _element(element: ElementReport) -> dict[str, Any]:
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
        "produced": {name: encoded(value) for name, value in element.produced.items()},
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


def encoded(value: Any) -> dict[str, Any]:
    """A produced value, as the report writes it: ``{"value": ...}`` if it is JSON, and
    ``{"repr": ..., "type": ...}`` otherwise."""
    if _is_json(value, set()):
        return {"value": _plain(value)}
    return {"repr": _repr(value), "type": _type_name(type(value))}


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


def _repr(value: Any) -> str:
    try:
        text = repr(value)
    except Exception as error:  # a broken __repr__ must not break the report
        return f"<{_type_name(type(value))} object: repr() raised {type(error).__name__}>"
    if len(text) > _REPR_LIMIT:
        return text[: _REPR_LIMIT - 1] + "…"
    return text


def _type_name(kind: type) -> str:
    if kind.__module__ == "builtins":
        return kind.__qualname__
    return f"{kind.__module__}.{kind.__qualname__}"
