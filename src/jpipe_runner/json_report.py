"""The JSON report: the machine-readable contract of a run (ADR-0011).

``document(report)`` is the report as a JSON document, which ``report.schema.json``, shipped
in the package, describes; ``dumps(report)`` is its text. The document is versioned by
``schema_version``: within a major version, a minor version only adds optional fields, so
a consumer ignores the fields it does not know.

It is deterministic: two runs over the same files give the same document. It holds no
time, duration or host name, paths are relative to where the runner runs, and keys come
in a fixed order. A produced value that is not JSON (a ``Path``, a ``datetime``, an object,
a float that is not finite) is written as its ``repr`` and its type, never refused. That
``repr`` is made canonical (``records``): a path under the run's root is shown relative to
it, the items of a set are sorted, and an object's address is left out, at any depth. A
value is written as it was when the run saw it, even one that could not be copied.
"""

import json
import math
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any

from jpipe_runner.diagnostics import Diagnostic
from jpipe_runner.observables import HIDDEN, Observation
from jpipe_runner.records import Decoded, Uncopied, canonical_repr, type_name
from jpipe_runner.report import ElementReport, RunReport, Selection, Summary, Trace

SCHEMA_VERSION = "2.1"

SCHEMA: dict[str, Any] = json.loads(
    files("jpipe_runner").joinpath("schema/report.schema.json").read_text(encoding="utf-8")
)


def document(report: RunReport) -> dict[str, Any]:
    """``report`` as a JSON document, as ``report.schema.json`` describes it."""
    return {
        "schema_version": SCHEMA_VERSION,
        "justification": report.justification,
        "verdict": str(report.verdict),
        "strict": report.strict,
        "summary": summary(report.summary),
        "elements": [element(each, report.root) for each in report.elements],
        "diagnostics": [diagnostic(each, report.root) for each in report.diagnostics],
        "diagram": report.diagram,
        "selection": _selection(report.selection),
    }


def _selection(selection: Selection | None) -> dict[str, Any] | None:
    if selection is None:
        return None
    return {"baseline": selection.baseline, "rerun": dict(selection.rerun)}


def dumps(report: RunReport) -> str:
    """The text of ``report``'s JSON document: indented by two spaces, in UTF-8, with a
    final newline."""
    return json.dumps(document(report), indent=2, ensure_ascii=False) + "\n"


def summary(counted: Summary) -> dict[str, Any]:
    """A report's summary, as the report writes it."""
    return {
        "elements": counted.elements,
        "pass": counted.passed,
        "fail": counted.failed,
        "skip": counted.skipped,
        "not_run": counted.not_run,
        "errors": counted.errors,
        "warnings": counted.warnings,
    }


def element(element: ElementReport, root: Path = Path()) -> dict[str, Any]:
    """An element of a report, as the report writes it, with paths relative to ``root``."""
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
        "reused": element.reused,
        "bound_to": element.step,
        "bound_by": list(element.designators),
        "library_sha256": element.library_sha256,
        "observes": list(element.observes),
        "sources": list(element.sources),
        "consumes": list(element.consumes),
        "inputs": {
            each.parameter: {"variable": each.variable, "produced_by": each.produced_by}
            for each in element.inputs
        },
        "produces": list(element.produces),
        "produced": {name: encoded(value, root) for name, value in element.produced.items()},
        "artifacts": [_artifact(seen, root) for seen in element.artifacts if seen.path],
        "observations": [_observation(seen, root) for seen in element.artifacts if not seen.path],
    }


def _artifact(artifact: Observation, root: Path) -> dict[str, Any]:
    """A file that was observed. It carries a value when what was observed is one in it.
    One that was read, without what was observed in it being found, is unreachable: its
    SHA-256 and size are in ``read``, so that ``sha256`` is null exactly when it is."""
    reached = artifact.reachable
    written: dict[str, Any] = {
        "path": artifact.path,
        "declared": artifact.declared,
        "reachable": reached,
        "sha256": artifact.sha256 if reached else None,
        "size": artifact.size if reached else None,
    }
    if not reached and artifact.sha256 is not None:
        written["read"] = {"sha256": artifact.sha256, "size": artifact.size}
    if artifact.value is not HIDDEN:
        written["value"] = encoded(artifact.value, root)
    return written


def _observation(observation: Observation, root: Path) -> dict[str, Any]:
    """Something observed that is not a file."""
    shown = observation.value is not HIDDEN
    return {
        "declared": observation.declared,
        "variable": observation.variable,
        "reachable": observation.reachable,
        "hidden": observation.hidden,
        "sha256": observation.sha256,
        "value": encoded(observation.value, root) if shown else None,
    }


def diagnostic(diagnostic: Diagnostic, root: Path = Path()) -> dict[str, Any]:
    """A diagnostic, as the report writes it, with its traceback's paths relative to
    ``root``."""
    trace = Trace.carried_by(diagnostic, root)
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
    """A produced value, as the report writes it: ``{"value": ...}`` if it is JSON, with
    its ``type`` if JSON reads it back as another, and ``{"repr": ..., "type": ...}``
    otherwise, with a canonical ``repr`` (paths shown relative to ``root``). One that could
    not be copied is written as it was when the run saw it (``records.Uncopied``), and one
    taken from an earlier report as that report wrote it (``records.Decoded``)."""
    if isinstance(value, Uncopied):
        return {"repr": value.repr, "type": value.type}
    if isinstance(value, Decoded):
        return {"value": value.value, "type": value.type}
    if not _is_json(value, set()):
        return {"repr": canonical_repr(value, root), "type": type_name(type(value))}
    if _exact(value):
        return {"value": value}
    return {"value": _plain(value), "type": type_name(type(value))}


def _is_json(value: Any, seen: set[int]) -> bool:
    """Whether ``value`` is JSON as it is: ``None``, a ``bool``, an ``int`` Python can
    write, a finite ``float``, a ``str``, or a list, tuple or mapping with ``str`` keys of
    such values."""
    if value is None or isinstance(value, bool | str):
        return True
    if isinstance(value, int):
        return _writable(value)
    if isinstance(value, float):
        return math.isfinite(value)
    if not isinstance(value, list | tuple | Mapping) or id(value) in seen:
        return False
    seen = seen | {id(value)}
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _is_json(v, seen) for key, v in value.items())
    return all(_is_json(item, seen) for item in value)


def _exact(value: Any) -> bool:
    """Whether JSON reads ``value``, which is JSON, back as it is: no tuple, enum, subclass
    or mapping other than a ``dict``, at any depth."""
    if type(value) in (type(None), bool, int, float, str):
        return True
    if type(value) is list:
        return all(_exact(item) for item in value)
    return type(value) is dict and all(
        type(key) is str and _exact(item) for key, item in value.items()
    )


def _writable(value: int) -> bool:
    """Whether Python writes ``value`` in decimal: not if it has more digits than
    ``sys.get_int_max_str_digits()`` allows."""
    try:
        int.__repr__(value)
    except ValueError:
        return False
    return True


def _plain(value: Any) -> Any:
    """``value``, which is JSON, with its containers as lists and dicts."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value
