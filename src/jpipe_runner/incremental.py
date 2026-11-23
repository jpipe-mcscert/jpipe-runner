"""Incremental runs: what changed since an earlier run runs again, the rest is reused (ADR-0039).

``jpipe-runner --incremental REPORT`` names the JSON report of an earlier run, the
baseline. Once validation passed, ``Baseline.reuse`` compares the run about to start with
it, and says which elements to take as the baseline decided them, rather than run again.
An element runs again when the baseline cannot stand for this run (it ran no step, it is of
another justification, or the model changed), when its step's declarations or its
library changed, when something it observed changed since, as ``jpipe-runner status``
finds it, or cannot be checked from the report, and when it is above an element that runs
again. A step that runs again receives the values of the elements reused as the baseline
holds them, as JSON; one it holds only as a ``repr`` makes its producer run again.

What runs again is closed upwards, so an element reused has only reused supporters, and the
baseline's decision still holds. It is reused whole: its status, reason, ``blocked_by``,
what it observed, produced and reported, tracebacks included.
"""

import logging
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

from jpipe_runner import impact, json_report
from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.engine import ElementResult, RunResult, Status
from jpipe_runner.observables import HIDDEN, Observation, Obstacle
from jpipe_runner.records import Uncopied
from jpipe_runner.report import RunReport, Selection
from jpipe_runner.rules import RULES

_LOG = logging.getLogger(__name__)

Document = Mapping[str, Any]

_VALIDATION = frozenset(rule.code for rule in RULES)
"""The codes of validation's diagnostics: validation runs again in every run, so those of
an element reused are its own, not the baseline's."""

_DECLARATIONS = ("bound_to", "bound_by", "observes", "sources", "consumes", "inputs", "produces")
"""What an element's step declares, as the report writes it: if any of it differs from the
baseline's, the step is not the one the baseline ran."""


class Baseline:
    """The report an incremental run compares with, and, once the run started, what it ran
    again (``selection``)."""

    def __init__(self, given: str, document: Document | None, root: Path = Path()) -> None:
        self._given = given
        self._document = document
        self._root = root
        self.selection: Selection | None = None
        """What the run ran again, and why: set by ``reuse``."""

    @classmethod
    def read(cls, given: str, root: Path = Path()) -> "Baseline":
        """The report at ``given``, a path relative to the working directory, as the command
        line gave it. A file that does not exist is no baseline: everything runs again.
        Raises ``OSError`` if it cannot be read, and ``impact.InvalidReportError`` if it is
        not a report of a version this runner reads."""
        path = Path(given)
        if not path.exists():
            _LOG.warning("%s does not exist: every element runs", given)
            return cls(given, None, root)
        return cls(given, impact.read(path), root)

    def reuse(self, planned: RunResult) -> dict[str, ElementResult]:
        """The result of each element of ``planned``, the result a dry run would have
        returned, to take from the baseline rather than run again, by id; and, in
        ``selection``, why each other one runs again."""
        now = json_report.document(RunReport.of(planned, self._root))
        order = [element["id"] for element in now["elements"]]
        rerun = _rerun(self._document, now, self._root)
        self.selection = Selection(
            self._given, MappingProxyType({i: rerun[i] for i in order if i in rerun})
        )
        if self._document is None:
            return {}
        recorded = {element["id"]: element for element in self._document["elements"]}
        diagnostics = self._document["diagnostics"]
        return {
            element.id: _decoded(planned, recorded[element.id], diagnostics)
            for element in planned.justification.topological_order()
            if element.id not in rerun
        }


def _rerun(baseline: Document | None, now: Document, root: Path) -> dict[str, str]:
    """Each element of ``now`` to run again, and why."""
    every = [element["id"] for element in now["elements"]]
    if baseline is None:
        return dict.fromkeys(every, "there is no baseline")
    if (unusable := _unusable(baseline, now)) is not None:
        return dict.fromkeys(every, unusable)
    recorded = {element["id"]: element for element in baseline["elements"]}
    rerun: dict[str, str] = {}
    for element in now["elements"]:
        why = next(_changed(element, recorded[element["id"]]), None)
        if why is not None:
            rerun[element["id"]] = why
    for change in impact.stale(baseline, root):
        rerun.setdefault(change.element, f"{change.path} {change.kind}")
    for unchecked in impact.unverified(baseline):
        rerun.setdefault(unchecked.element, f"{unchecked.declared} cannot be checked again")
    while True:
        _above(now, rerun)
        needed = dict(_producers(now, recorded, rerun))
        if not needed:
            return rerun
        rerun.update(needed)


def _unusable(baseline: Document, now: Document) -> str | None:
    """Why ``baseline`` cannot stand for the run of ``now`` at all, if it cannot."""
    if baseline["verdict"] in ("invalid", "valid"):
        return "the baseline ran no step"
    if baseline["justification"] != now["justification"]:
        return f"the baseline is a run of {baseline['justification']!r}"
    if _shape(baseline) != _shape(now):
        return "the model changed"
    return None


def _shape(document: Document) -> set[tuple[str, str, tuple[str, ...]]]:
    """The elements of a report, their kinds, and what each supports."""
    return {
        (element["id"], element["kind"], tuple(sorted(element["supports"])))
        for element in document["elements"]
    }


def _changed(element: Document, recorded: Document) -> Iterator[str]:
    """Why ``element``'s step is not the one the baseline ``recorded``, if it is not."""
    if any(element[key] != recorded.get(key) for key in _DECLARATIONS):
        yield "its step's declarations changed"
    if element["bound_to"] is not None and (
        element["library_sha256"] is None
        or element["library_sha256"] != recorded.get("library_sha256")
    ):
        yield "its step's library changed"


def _above(now: Document, rerun: dict[str, str]) -> None:
    """Add to ``rerun`` every element above one in it, naming the supporter that reruns."""
    supporters: dict[str, list[str]] = {}
    for element in now["elements"]:
        for supported in element["supports"]:
            supporters.setdefault(supported, []).append(element["id"])
    for element in now["elements"]:  # in topological order: supporters first
        if element["id"] not in rerun:
            running = [s for s in supporters.get(element["id"], ()) if s in rerun]
            if running:
                rerun[element["id"]] = f"{running[0]} runs again"


def _producers(
    now: Document, recorded: Mapping[str, Document], rerun: Mapping[str, str]
) -> Iterator[tuple[str, str]]:
    """Each element reused that a step running again consumes a value from, held by the
    baseline only as its ``repr``, and why it must run again."""
    for element in now["elements"]:
        if element["id"] not in rerun:
            continue
        for received in element["inputs"].values():
            producer, variable = received["produced_by"], received["variable"]
            if producer in rerun:
                continue
            value = recorded[producer]["produced"].get(variable, {})
            if "value" not in value:
                yield (
                    producer,
                    f"{element['id']} consumes {variable!r}, which the baseline records only "
                    "as its repr",
                )


def _decoded(
    planned: RunResult, recorded: Document, diagnostics: Iterable[Document]
) -> ElementResult:
    """The element as the baseline ``recorded`` it, for the run of ``planned``."""
    element = planned.justification.element(recorded["id"])
    observed = tuple(
        [_artifact(artifact) for artifact in recorded["artifacts"]]
        + [_observation(observation) for observation in recorded.get("observations", [])]
    )
    return ElementResult(
        element,
        Status(recorded["status"]),
        planned.bindings.binding_for(element.id),
        recorded["reason"],
        tuple(recorded["blocked_by"]),
        ran=recorded["ran"],
        produced=MappingProxyType(
            {name: _value(value) for name, value in recorded["produced"].items()}
        ),
        observed=observed,
        reached=_reached(recorded["sources"], observed),
        diagnostics=tuple(
            _diagnostic(each)
            for each in diagnostics
            if each["element"] == element.id and each["code"] not in _VALIDATION
        ),
        reused=True,
    )


def _value(encoded: Mapping[str, Any]) -> Any:
    """A value as the report wrote it (``json_report.encoded``): itself, or its ``repr``."""
    if "value" in encoded:
        return encoded["value"]
    return Uncopied(encoded["repr"], encoded["type"])


_UNREACHED = "the baseline recorded it as unreachable"


def _artifact(artifact: Mapping[str, Any]) -> Observation:
    """A file observed, as the report wrote it."""
    read = artifact.get("read", {})
    reached = artifact["reachable"]
    return Observation(
        artifact["declared"],
        artifact["path"],
        artifact["sha256"] if reached else read.get("sha256"),
        artifact["size"] if reached else read.get("size"),
        None if reached else Obstacle(artifact["path"], _UNREACHED),
        _value(artifact["value"]) if "value" in artifact else HIDDEN,
    )


def _observation(observation: Mapping[str, Any]) -> Observation:
    """Something observed that is not a file, as the report wrote it."""
    reached, value = observation["reachable"], observation["value"]
    return Observation(
        observation["declared"],
        sha256=observation["sha256"],
        obstacle=None if reached else Obstacle(observation["declared"], _UNREACHED),
        value=HIDDEN if value is None else _value(value),
        variable=observation["variable"],
        hidden=observation["hidden"],
    )


def _reached(
    sources: Iterable[str], observed: tuple[Observation, ...]
) -> tuple[tuple[str, bool], ...]:
    """Whether each source was reached: every observation under its name was."""
    return tuple(
        (source, all(seen.reachable for seen in observed if seen.declared == source))
        for source in sources
    )


def _diagnostic(recorded: Mapping[str, Any]) -> Diagnostic:
    """A diagnostic as the report wrote it, with its traceback as recorded."""
    return Diagnostic(
        recorded["code"],
        Severity(recorded["severity"]),
        recorded["message"],
        recorded["element"],
        recorded["fix"],
        recorded=recorded["traceback"],
    )
