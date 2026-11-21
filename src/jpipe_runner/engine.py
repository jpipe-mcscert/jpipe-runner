"""The engine: running a step library against its model, supporters first (ADR-0021).

``run`` validates the library against the model (ADR-0010), and runs it only if no
error was reported. Each element is then taken in topological order:

- an element a supporter of which did not pass is **skipped**, and ``blocked_by`` names
  the elements upstream that stopped it: those that failed, or were skipped, on their own
  account. Its step is not called. A failure and a skip propagate alike: what a step
  that did not pass would have produced does not exist;
- otherwise, a **bound** element's step is called, whatever its kind, with the values it
  consumes, each from the supporter validation resolved it to (ADR-0031), and the
  artifacts it observes, and what it returns is the element's status;
- an **unbound** conclusion or sub-conclusion passes, since all its supporters passed.
  One that nothing supports is skipped: nothing judges it.

A step's mistakes fail its element, with a diagnostic, and the run goes on: an exception
(``JP022``), anything but an outcome (``JP017``), an unreachable artifact (``JP019``), or
a ``Pass`` without a value the step declares (``JP023``). A value a ``Pass`` carries
without declaring it is dropped, with a warning (``JP024``).

The verdict is ``FAIL`` if an element failed, ``SKIP`` if one was skipped, and ``PASS``
otherwise; ``INVALID`` when validation stopped the run. A dry run validates and calls no
step: its verdict is ``VALID`` when validation passed (ADR-0024).

A ``RunListener`` is told as the run goes: when validation ends, when the steps are about
to run, with the result a dry run would have returned (ADR-0032), when an element's step is
about to be called, and when each element is decided (ADR-0030). It is called from the
thread that runs ``run``, an element after all its supporters, so it needs no lock.
"""

import logging
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from traceback import TracebackException
from types import MappingProxyType
from typing import Any, Protocol

from jpipe_runner.artifacts import UNREACHABLE_ARTIFACT, observe
from jpipe_runner.binding import Binding, BindingTable
from jpipe_runner.dataflow import Consumption, DataflowTable, Received
from jpipe_runner.diagnostics import Diagnostic, Severity, shown_path, user_traceback
from jpipe_runner.model import Element, Justification
from jpipe_runner.observables import Context, Observation, snapshot
from jpipe_runner.outcomes import Fail, NotAnOutcomeError, Outcome, Pass, Skip, as_outcome
from jpipe_runner.rules import RULES
from jpipe_runner.steps import StepRegistry
from jpipe_runner.validation import ValidationContext, ValidationReport
from jpipe_runner.values import UNSET, ValueStore

STEP_RAISED = "JP022"
DECLARED_VALUE_MISSING = "JP023"
UNDECLARED_VALUE = "JP024"

_LOG = logging.getLogger(__name__)


class Status(StrEnum):
    """What a run concluded about an element."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"


class Verdict(StrEnum):
    """What a run concluded about the justification."""

    PASS = "pass"
    """Every element passed."""
    FAIL = "fail"
    """An element failed."""
    SKIP = "skip"
    """No element failed, and one was skipped: the justification is not established."""
    INVALID = "invalid"
    """Validation reported an error, so nothing ran."""
    VALID = "valid"
    """A dry run: validation reported no error, and no step was called."""


@dataclass(frozen=True)
class ElementResult:
    """What happened to one element in a run."""

    element: Element
    status: Status
    binding: Binding | None = None
    """The step bound to the element and the ids that bound it, or ``None`` if unbound."""
    reason: str | None = None
    """Why it did not pass: the step's reason, the problem, or the elements blocking it."""
    blocked_by: tuple[str, ...] = ()
    """The ids of the elements upstream that stopped it, failed or skipped on their own
    account, in model order. Empty unless it was skipped because of them."""
    ran: bool = False
    """Whether its step was called."""
    outcome: Outcome | None = None
    """What its step returned, if it returned an outcome."""
    produced: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    """The values it produced, as they were when it returned: a copy, so that a step it
    supports cannot change the record by changing the value it receives."""
    observed: tuple[Observation, ...] = ()
    """What its step observed, recorded just before the call."""
    diagnostics: tuple[Diagnostic, ...] = ()
    """What went wrong while running it. A step that raised is reported with ``JP022``,
    which carries the traceback."""
    inputs: tuple[Received, ...] = ()
    """What each parameter of its step receives, and from which element: whether the step
    was called or not."""


class RunListener(Protocol):
    """What is told of a run as it goes, before ``run`` returns its ``RunResult``."""

    def validation_ended(self, report: ValidationReport) -> None:
        """Validation is over: the steps run next, unless it reported an error or the run
        is a dry run."""

    def steps_starting(self, planned: "RunResult") -> None:
        """Validation passed, and the steps are about to run: ``planned`` is the result a
        dry run of the same library would have returned, with no element decided. Told
        once, before the first element starts, and never in a dry run."""

    def element_started(self, element: Element) -> None:
        """``element``'s supporters passed, and it is bound: the artifacts it observes are
        about to be observed, then its step called, unless one of them cannot be reached."""

    def element_decided(self, result: ElementResult) -> None:
        """``result.element`` is decided: after every element that supports it."""


class _Silent:
    """The listener of a run that nothing listens to."""

    def validation_ended(self, report: ValidationReport) -> None:
        pass  # nothing listens

    def steps_starting(self, planned: "RunResult") -> None:
        pass  # nothing listens

    def element_started(self, element: Element) -> None:
        pass  # nothing listens

    def element_decided(self, result: ElementResult) -> None:
        pass  # nothing listens


@dataclass(frozen=True)
class RunResult:
    """The outcome of a run: validation, then each element's result, in the order run."""

    justification: Justification
    bindings: BindingTable
    dataflow: DataflowTable
    """Where each value a bound step consumes comes from."""
    validation: ValidationReport
    elements: tuple[ElementResult, ...]
    """One per element, in topological order. Empty when validation stopped the run."""
    values: ValueStore
    strict: bool = False
    """Whether validation counted warnings as errors."""
    dry_run: bool = False
    """Whether the run stopped after validation, calling no step."""

    @property
    def verdict(self) -> Verdict:
        if not self.validation.passed:
            return Verdict.INVALID
        if self.dry_run:
            return Verdict.VALID
        statuses = {result.status for result in self.elements}
        if Status.FAIL in statuses:
            return Verdict.FAIL
        return Verdict.SKIP if Status.SKIP in statuses else Verdict.PASS

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        """What validation reported, then what each element's run did, in the order run."""
        found = [d for result in self.elements for d in result.diagnostics]
        return (*self.validation.diagnostics, *found)

    def result(self, element_id: str) -> ElementResult:
        """The result of the element whose own id is ``element_id``."""
        for result in self.elements:
            if result.element.id == element_id:
                return result
        raise KeyError(f"no result for {element_id!r}")

    def __iter__(self) -> Iterator[ElementResult]:
        return iter(self.elements)


def run(
    justification: Justification,
    registry: StepRegistry,
    *,
    strict: bool = False,
    root: Path = Path(),
    dry_run: bool = False,
    listener: RunListener | None = None,
) -> RunResult:
    """Validate ``registry`` against ``justification``, then run it if nothing is an error.

    ``strict`` counts validation warnings as errors. ``root``, by default the working
    directory, is what the paths of the report are relative to; the paths an evidence
    observes are relative to the file that declares its step. A ``dry_run`` stops after
    validation, and calls no step. The steps run in this process: a run of libraries
    imported with ``libraries.imported`` happens inside that context. ``listener`` is told
    of the run as it goes.
    """
    listener = _Silent() if listener is None else listener
    ctx = ValidationContext.of(justification, registry)
    report = RULES.run(ctx, strict=strict)
    listener.validation_ended(report)
    if not report.passed:
        _LOG.info("validation reported %d errors: nothing runs", len(report.errors))
        return RunResult(
            justification, ctx.bindings, ctx.dataflow, report, (), ValueStore(), strict
        )
    # What a dry run returns, and what a listener is told the run plans.
    planned = RunResult(
        justification, ctx.bindings, ctx.dataflow, report, (), ValueStore(), strict, dry_run=True
    )
    if dry_run:
        _LOG.info("validation passed: a dry run calls no step")
        return planned
    listener.steps_starting(planned)
    values = ValueStore()
    elements = _Run(ctx, values, root, listener).execute()
    return RunResult(justification, ctx.bindings, ctx.dataflow, report, elements, values, strict)


class _Run:
    """One execution of a validated library: the results so far, and the values produced."""

    def __init__(
        self, ctx: ValidationContext, values: ValueStore, root: Path, listener: RunListener
    ) -> None:
        self._model = ctx.justification
        self._bindings = {binding.element.id: binding for binding in ctx.bindings}
        self._dataflow = ctx.dataflow
        self._rank = {element.id: rank for rank, element in enumerate(self._model)}
        self._values = values
        self._root = root
        self._listener = listener
        self._results: dict[str, ElementResult] = {}

    def execute(self) -> tuple[ElementResult, ...]:
        for element in self._model.topological_order():
            result = self._result_of(element)
            if result.binding is not None:
                result = replace(result, inputs=self._dataflow.received(element.id))
            _LOG.info("%s %s: %s", result.status, element.id, result.reason or "")
            self._results[element.id] = result
            self._listener.element_decided(result)
        return tuple(self._results.values())

    def _result_of(self, element: Element) -> ElementResult:
        binding = self._bindings.get(element.id)
        supporters = self._model.supporters(element.id)
        if binding is None and not supporters:
            return ElementResult(element, Status.SKIP, reason="nothing supports it or checks it")
        if blocked_by := self._blocking(supporters):
            reason = f"not run: {', '.join(blocked_by)} did not pass"
            return ElementResult(element, Status.SKIP, binding, reason, blocked_by)
        if binding is None:
            return ElementResult(element, Status.PASS)
        self._listener.element_started(element)
        return self._call(binding)

    def _blocking(self, supporters: tuple[Element, ...]) -> tuple[str, ...]:
        """The elements that stop an element so supported: each supporter that did not
        pass on its own account, and what stopped those that were stopped."""
        roots: set[str] = set()
        for supporter in supporters:
            result = self._results[supporter.id]
            if result.status is not Status.PASS:
                roots.update(result.blocked_by or (supporter.id,))
        return tuple(sorted(roots, key=self._rank.__getitem__))

    def _call(self, binding: Binding) -> ElementResult:
        element, step = binding.element, binding.step
        observed = observe(step.observes, Context(step.directory, self._root), element.id)
        if not observed.reachable:
            return _failed(binding, observed.diagnostics, observed=observed.observations)
        arguments = {c.input.parameter: self._consumed(c) for c in self._dataflow.of(element.id)}
        arguments.update(observed.arguments)
        _LOG.debug("calling %s for %s", step.name, element.id)
        try:
            returned = step.function(**arguments)
        # A step that calls sys.exit() fails its element, rather than end the run without a
        # report; KeyboardInterrupt still stops it (ADR-0021).
        except (Exception, SystemExit) as error:  # NOSONAR
            raised = _raised(element, error, user_traceback(error), self._root)
            return _failed(binding, (raised,), observed=observed.observations)
        try:
            outcome = as_outcome(returned, element.id)
        except NotAnOutcomeError as error:
            return _failed(binding, (error.diagnostic,), observed=observed.observations)
        return self._judged(binding, outcome, observed.observations)

    def _consumed(self, consumed: Consumption) -> Any:
        # Validation guarantees one producer among the consumer's supporters (JP009, JP014,
        # JP025), and an element runs only once its supporters passed, which stored what
        # they declare (JP023).
        producer, name = consumed.producer, consumed.input.variable
        value = UNSET if producer is None else self._values.get(name, producer.element.id)
        if value is UNSET:
            element = consumed.consumer.element.id
            raise RuntimeError(f"{element!r} consumes {name!r}, which is unset: a runner bug")
        return value

    def _judged(
        self, binding: Binding, outcome: Outcome, observed: tuple[Observation, ...]
    ) -> ElementResult:
        if isinstance(outcome, Pass):
            return self._passed(binding, outcome, observed)
        status = Status.FAIL if isinstance(outcome, Fail) else Status.SKIP
        reason = outcome.reason if isinstance(outcome, Fail | Skip) else None
        return ElementResult(
            binding.element,
            status,
            binding,
            reason or None,
            ran=True,
            outcome=outcome,
            observed=observed,
        )

    def _passed(
        self, binding: Binding, outcome: Pass, observed: tuple[Observation, ...]
    ) -> ElementResult:
        """The step passed: store what it declares it produces, unless something is missing."""
        element, step = binding.element, binding.step
        problems = list(_undeclared(binding, outcome.values))
        if missing := [name for name in step.produces if name not in outcome.values]:
            problems.append(_missing(binding, missing))
            return _failed(binding, problems, observed=observed, outcome=outcome)
        produced = {name: outcome.values[name] for name in step.produces}
        for name, value in produced.items():
            self._values.put(name, value, element.id)
        return ElementResult(
            element,
            Status.PASS,
            binding,
            ran=True,
            outcome=outcome,
            produced=MappingProxyType({name: snapshot(v) for name, v in produced.items()}),
            observed=observed,
            diagnostics=tuple(problems),
        )


def _failed(
    binding: Binding,
    diagnostics: Sequence[Diagnostic],
    *,
    observed: tuple[Observation, ...],
    outcome: Outcome | None = None,
) -> ElementResult:
    """The element failed because of ``diagnostics``. Its step ran, unless an artifact was
    unreachable."""
    errors = [d.message for d in diagnostics if d.severity is Severity.ERROR]
    ran = not any(d.code == UNREACHABLE_ARTIFACT for d in diagnostics)
    return ElementResult(
        binding.element,
        Status.FAIL,
        binding,
        "; ".join(errors),
        ran=ran,
        outcome=outcome,
        observed=observed,
        diagnostics=tuple(diagnostics),
    )


def _raised(
    element: Element, error: BaseException, trace: TracebackException, root: Path
) -> Diagnostic:
    # Where comes before the exception's own message, which may end a sentence.
    raised = type(error).__name__
    if trace.stack:
        frame = trace.stack[-1]
        raised += f" at {shown_path(frame.filename, root)}, line {frame.lineno}"
    return Diagnostic(
        STEP_RAISED,
        Severity.ERROR,
        f"the step raised {raised}{_said(error)}",
        element=element.id,
        fix="Return Fail(reason) when the check does not hold: an exception says the step "
        "itself is broken.",
        traceback=trace,
    )


def _said(error: BaseException) -> str:
    """``error``'s message, after a colon, if it has one."""
    message = str(error)
    return f": {message}" if message else ""


def _missing(binding: Binding, names: list[str]) -> Diagnostic:
    listed = ", ".join(map(repr, names))
    return Diagnostic(
        DECLARED_VALUE_MISSING,
        Severity.ERROR,
        f"{binding.step.name} returned Pass without {listed}, which it declares it produces",
        element=binding.element.id,
        fix=f"Return Pass({names[0]}=...), or remove {names[0]!r} from produces=[...].",
    )


def _undeclared(binding: Binding, values: Mapping[str, Any]) -> Iterator[Diagnostic]:
    if names := [name for name in values if name not in binding.step.produces]:
        listed = ", ".join(map(repr, names))
        yield Diagnostic(
            UNDECLARED_VALUE,
            Severity.WARNING,
            f"{binding.step.name} returned {listed} in Pass without declaring it: dropped",
            element=binding.element.id,
            fix=f"Declare it, produces=[{names[0]!r}, ...], or stop returning it.",
        )
