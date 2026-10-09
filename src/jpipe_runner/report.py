"""The report of a run: what the runner concluded, as data that renderers turn into text,
JSON or a diagram (ADR-0011).

A ``RunReport`` is built for every way a run can end, including those in which nothing ran:

- ``RunReport.of(result)``: a run, whether validation let the steps run or not;
- ``RunReport.refused(error)``: a model the loader refused (JP001 to JP004);
- ``RunReport.not_imported(justification, error)``: step libraries that could not be
  imported (JP020, JP021).

It lists the model's elements in topological order, each with its status (``None`` when
nothing ran), the step bound to it and what that step declares, and what the run observed
and produced; then every diagnostic, in the order found. A report is plain data, built
once: the renderers are pure functions of it, and the engine prints nothing.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from traceback import FrameSummary, TracebackException
from types import MappingProxyType
from typing import Any

from jpipe_runner.artifacts import Observation
from jpipe_runner.binding import Binding
from jpipe_runner.diagnostics import Diagnostic, Severity, shown_path
from jpipe_runner.engine import ElementResult, RunResult, Status, Verdict
from jpipe_runner.libraries import LibraryLoadError
from jpipe_runner.model import Element, InvalidJustificationError, Justification, Kind

_NOTHING: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class ElementReport:
    """One element of the model, and what the run concluded about it."""

    id: str
    label: str
    kind: Kind
    aliases: tuple[str, ...] = ()
    supports: tuple[str, ...] = ()
    """The ids of the elements it supports, in model order."""
    status: Status | None = None
    """``None`` when nothing ran: the model was invalid, or a library could not be imported."""
    reason: str | None = None
    blocked_by: tuple[str, ...] = ()
    """The elements upstream that stopped it, failed or skipped on their own account."""
    ran: bool = False
    """Whether its step was called."""
    step: str | None = None
    """The step bound to it, ``module.function``, or ``None`` if it is unbound."""
    designators: tuple[str, ...] = ()
    """The step's ids that designate it."""
    observes: tuple[str, ...] = ()
    """The paths and globs its step declares it observes."""
    consumes: tuple[str, ...] = ()
    """The variables its step declares it consumes."""
    produces: tuple[str, ...] = ()
    """The variables its step declares it produces."""
    produced: Mapping[str, Any] = field(default_factory=lambda: _NOTHING)
    """The values its step produced, by variable."""
    artifacts: tuple[Observation, ...] = ()
    """The files its step observed, recorded just before the call."""


@dataclass(frozen=True)
class Summary:
    """How many elements ended in each status, and how many diagnostics of each severity."""

    elements: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    not_run: int = 0
    errors: int = 0
    warnings: int = 0


@dataclass(frozen=True)
class Frame:
    """One frame of a traceback, as the report shows it."""

    file: str
    """Relative to the run's root, in POSIX form, when the file is under it."""
    line: int | None
    function: str
    code: str | None
    """The source line, when it can be read."""


@dataclass(frozen=True)
class Trace:
    """An exception and its traceback, as the report shows it: deterministic, with paths
    relative to the run's root, and in the same form on every Python version."""

    exception: str
    """The exception's type, qualified by its module unless it is a built-in."""
    message: str
    frames: tuple[Frame, ...] = ()
    """From the outermost call to where it was raised."""
    cause: "Trace | None" = None
    """The exception this one was raised from, or while handling, if any."""

    @classmethod
    def of(cls, trace: TracebackException, root: Path = Path()) -> "Trace":
        cause = trace.__cause__
        if cause is None and not trace.__suppress_context__:
            cause = trace.__context__
        return cls(
            _type_name(trace),
            str(trace),
            tuple(_frame(frame, root) for frame in trace.stack),
            None if cause is None else cls.of(cause, root),
        )


@dataclass(frozen=True)
class RunReport:
    """What a run concluded, for every element of its model, and every diagnostic."""

    justification: str | None
    """The model's name, or ``None`` if the model was refused."""
    verdict: Verdict
    elements: tuple[ElementReport, ...] = ()
    """Every element of the model, in topological order; none if the model was refused."""
    diagnostics: tuple[Diagnostic, ...] = ()
    """Every problem found, in the order found: loading, importing or validation, then
    each element's run."""
    strict: bool = False
    """Whether validation counted warnings as errors."""
    diagram: str | None = None
    """Where the diagram of the run was written, if one was."""
    root: Path = field(default=Path(), compare=False)
    """The directory the run observed artifacts from: tracebacks are shown relative to it."""

    @classmethod
    def of(cls, result: RunResult, root: Path = Path()) -> "RunReport":
        """The report of ``result``, a run whose artifacts were observed under ``root``."""
        bindings = {binding.element.id: binding for binding in result.bindings}
        results = {element.element.id: element for element in result.elements}
        elements = tuple(
            _element(result.justification, element, bindings.get(element.id), results)
            for element in result.justification.topological_order()
        )
        return cls(
            result.justification.name,
            result.verdict,
            elements,
            result.diagnostics,
            result.strict,
            root=root,
        )

    @classmethod
    def refused(cls, error: InvalidJustificationError, *, strict: bool = False) -> "RunReport":
        """The report of a model the loader refused: nothing was validated or run."""
        return cls(None, Verdict.INVALID, diagnostics=error.diagnostics, strict=strict)

    @classmethod
    def not_imported(
        cls,
        justification: Justification,
        error: LibraryLoadError,
        *,
        strict: bool = False,
        root: Path = Path(),
    ) -> "RunReport":
        """The report of a run whose step libraries could not be imported: nothing was
        bound, validated or run."""
        elements = tuple(
            _element(justification, element, None, {})
            for element in justification.topological_order()
        )
        return cls(
            justification.name,
            Verdict.INVALID,
            elements,
            error.diagnostics,
            strict,
            root=root,
        )

    @property
    def summary(self) -> Summary:
        statuses = [element.status for element in self.elements]
        severities = [diagnostic.severity for diagnostic in self.diagnostics]
        return Summary(
            elements=len(self.elements),
            passed=statuses.count(Status.PASS),
            failed=statuses.count(Status.FAIL),
            skipped=statuses.count(Status.SKIP),
            not_run=statuses.count(None),
            errors=severities.count(Severity.ERROR),
            warnings=severities.count(Severity.WARNING),
        )

    @property
    def ran(self) -> bool:
        """Whether the steps were run: the model loaded, the libraries were imported, and
        validation reported no error."""
        return self.verdict is not Verdict.INVALID

    def trace(self, diagnostic: Diagnostic) -> Trace | None:
        """The traceback ``diagnostic`` carries, as the report shows it, if it carries one."""
        if diagnostic.traceback is None:
            return None
        return Trace.of(diagnostic.traceback, self.root)

    def with_diagram(self, path: str) -> "RunReport":
        """This report, recording that its diagram was written at ``path``."""
        return replace(self, diagram=path)


def _element(
    model: Justification,
    element: Element,
    binding: Binding | None,
    results: Mapping[str, ElementResult],
) -> ElementReport:
    report = ElementReport(
        element.id,
        element.label,
        element.kind,
        element.aliases,
        tuple(supported.id for supported in model.supported(element.id)),
    )
    if binding is not None:
        step = binding.step
        report = replace(
            report,
            step=step.name,
            designators=binding.designators,
            observes=tuple(artifact.path for artifact in step.observes),
            consumes=step.consumes,
            produces=step.produces,
        )
    result = results.get(element.id)
    if result is not None:
        report = replace(
            report,
            status=result.status,
            reason=result.reason,
            blocked_by=result.blocked_by,
            ran=result.ran,
            produced=result.produced,
            artifacts=result.observed,
        )
    return report


def _type_name(trace: TracebackException) -> str:
    named: str | None = getattr(trace, "exc_type_str", None)  # Python 3.13 and later
    if named is not None:
        return named
    exception = trace.exc_type
    if exception is None:
        return "Exception"
    if exception.__module__ in ("builtins", "__main__"):
        return exception.__qualname__
    return f"{exception.__module__}.{exception.__qualname__}"


def _frame(frame: FrameSummary, root: Path) -> Frame:
    return Frame(shown_path(frame.filename, root), frame.lineno, frame.name, frame.line or None)
