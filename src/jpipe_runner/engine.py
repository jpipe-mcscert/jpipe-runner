"""The engine: running a step library against its model, supporters first (ADR-0021).

``run`` validates the library against the model (ADR-0010), and runs it only if no
error was reported. Each element is then taken once every element that supports it is
decided, in topological order when one step runs at a time, the default; with more jobs,
independent steps run together, each on a thread of its own, and the result is the same,
in the same order (ADR-0038):

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
about to be called, when each source it observes was observed, and when each element is
decided (ADR-0030). It is called from the
thread that runs ``run``, whatever the number of jobs, an element after all its
supporters, so it needs no lock.
"""

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextvars import copy_context
from dataclasses import dataclass, field, replace
from enum import StrEnum
from heapq import heappop, heappush
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread
from traceback import TracebackException
from types import MappingProxyType
from typing import Any, Protocol

from jpipe_runner.artifacts import Observed, observe
from jpipe_runner.binding import Binding, BindingTable
from jpipe_runner.dataflow import Consumption, DataflowTable, Received
from jpipe_runner.diagnostics import Diagnostic, Severity, shown_path, user_traceback
from jpipe_runner.model import Element, Justification
from jpipe_runner.observables import Context, Observation
from jpipe_runner.outcomes import Fail, NotAnOutcomeError, Outcome, Pass, Skip, as_outcome
from jpipe_runner.records import snapshot
from jpipe_runner.rules import RULES
from jpipe_runner.steps import StepRegistry
from jpipe_runner.validation import ValidationContext, ValidationReport
from jpipe_runner.values import UNSET, ValueStore

STEP_RAISED = "JP022"
DECLARED_VALUE_MISSING = "JP023"
UNDECLARED_VALUE = "JP024"

_LOG = logging.getLogger(__name__)

_WAKE_UP = 0.1
"""How long, in seconds, the run waits for a step's thread before it looks again: a wait
that Ctrl-C can interrupt on every platform."""


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

    @property
    def ran(self) -> bool:
        """Whether a run with this verdict called its steps."""
        return self not in (Verdict.INVALID, Verdict.VALID)


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
    reached: tuple[tuple[str, bool], ...] = ()
    """Each source its step declares it observes, as the report names it in ``sources``,
    and whether it was reached, in the order the step declares them; empty when the step
    observed nothing, or was not called."""
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

    def source_observed(self, element: Element, source: str, reachable: bool) -> None:
        """What ``element``'s step declares it observes was observed: ``source``, as the
        report names it in ``sources``, and whether it was ``reachable``. Told for each,
        in the order the step declares them, once all are observed and before the step is
        called, if it is."""

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

    def source_observed(self, element: Element, source: str, reachable: bool) -> None:
        pass  # nothing listens

    def element_decided(self, result: ElementResult) -> None:
        pass  # nothing listens


@dataclass(frozen=True)
class RunResult:
    """The outcome of a run: validation, then each element's result, in topological
    order."""

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
        """What validation reported, then what each element's run did, in topological
        order."""
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
    jobs: int = 1,
) -> RunResult:
    """Validate ``registry`` against ``justification``, then run it if nothing is an error.

    ``strict`` counts validation warnings as errors. ``root``, by default the working
    directory, is what the paths of the report are relative to; the paths an evidence
    observes are relative to the file that declares its step. A ``dry_run`` stops after
    validation, and calls no step. The steps run in this process: a run of libraries
    imported with ``libraries.imported`` happens inside that context. ``listener`` is told
    of the run as it goes. ``jobs`` is how many steps may run at a time: with more than
    one, each on a thread of its own; the result is the same, in the same order (ADR-0038).
    """
    if jobs < 1:
        raise ValueError(f"a run needs at least one job, not {jobs}")
    listener = _Silent() if listener is None else listener
    ctx = ValidationContext.of(justification, registry)
    report = RULES.run(ctx, strict=strict)
    listener.validation_ended(report)
    # What a dry run returns, and what a listener is told the run plans.
    planned = RunResult(
        justification, ctx.bindings, ctx.dataflow, report, (), ValueStore(), strict, dry_run=True
    )
    if not report.passed:
        _LOG.info("validation reported %d errors: nothing runs", len(report.errors))
        # SonarCloud types dataclasses.replace as returning any dataclass (S5886); mypy --strict
        # checks the type.
        return replace(planned, dry_run=False)  # NOSONAR
    if dry_run:
        _LOG.info("validation passed: a dry run calls no step")
        return planned
    listener.steps_starting(planned)
    values = ValueStore()
    elements = _Run(ctx, values, root, listener, jobs).execute()
    # The values in the order of their producers, whatever order the steps ended in.
    values = values.sorted_by([result.element.id for result in elements])
    return replace(planned, elements=elements, values=values, dry_run=False)  # NOSONAR


class _Run:
    """One execution of a validated library: the results so far, the values produced, and
    the elements ready to be decided.

    An element is ready once every element that supports it is decided, and the ready one
    that comes first in topological order is taken first. With one job, its step is called
    on this thread, so the elements are decided in topological order. With more, an element
    is settled once, when it becomes ready: one that needs no step is decided at once,
    whatever the threads are doing, and up to ``jobs`` steps run at a time, each on a thread
    of its own, which observes the step's artifacts and calls it. What it observed, then
    what the step returned, come back through ``_inbox``, and everything else happens on
    this thread (ADR-0038).
    """

    def __init__(
        self,
        ctx: ValidationContext,
        values: ValueStore,
        root: Path,
        listener: RunListener,
        jobs: int,
    ) -> None:
        self._model = ctx.justification
        self._bindings = ctx.bindings
        self._dataflow = ctx.dataflow
        self._values = values
        self._root = root
        self._listener = listener
        self._jobs = jobs
        self._results: dict[str, ElementResult] = {}
        self._order = self._model.topological_order()
        self._position = {element.id: i for i, element in enumerate(self._order)}
        self._undecided = {e.id: len(self._model.supporters(e.id)) for e in self._order}
        # The positions, in topological order, of the ready elements to take: heaps. With
        # threads, those that need no step wait in _decidable, with their results, and only
        # those that do in _ready.
        self._ready: list[int] = []
        self._decidable: list[int] = []
        self._decided_at: dict[int, ElementResult] = {}
        self._bound_at: dict[int, Binding] = {}
        self._threads: list[Thread] = []
        self._inbox: SimpleQueue[_Sighted | _Attempt | BaseException] = SimpleQueue()
        self._running = 0
        for element in self._order:
            if not self._undecided[element.id]:
                self._became_ready(element)

    def execute(self) -> tuple[ElementResult, ...]:
        try:
            self._schedule()
        finally:
            # Once every element is decided, no step is left. A run stopped before
            # (KeyboardInterrupt) starts no other step, and waits for those still running,
            # which a thread cannot stop, while the libraries they run from are still
            # imported. A second Ctrl-C stops the wait, and, the threads being daemons, lets
            # the process exit.
            self._wait_for_steps()
        return tuple(self._results[element.id] for element in self._order)

    def _wait_for_steps(self) -> None:
        for thread in self._threads:
            while thread.is_alive():
                thread.join(_WAKE_UP)

    def _schedule(self) -> None:
        while self._decidable or self._ready or self._running:
            while self._decidable:
                self._decide(self._decided_at.pop(heappop(self._decidable)))
            while self._ready and self._running < self._jobs:
                self._take(heappop(self._ready))
            if self._running:
                for message in self._messages():
                    self._receive(message)

    def _became_ready(self, element: Element) -> None:
        """``element``'s supporters are all decided. With threads, one that needs no step
        is decided before any other step starts, so that a skip never waits for a slow step
        it does not depend on."""
        position = self._position[element.id]
        if self._jobs == 1:
            heappush(self._ready, position)
        elif isinstance(settled := self._settled(element), ElementResult):
            self._decided_at[position] = settled
            heappush(self._decidable, position)
        else:
            self._bound_at[position] = settled
            heappush(self._ready, position)

    def _settled(self, element: Element) -> ElementResult | Binding:
        """What ``element``, whose supporters are all decided, is without calling a step,
        or the binding whose step must be called."""
        binding = self._bindings.binding_for(element.id)
        supporters = self._model.supporters(element.id)
        if binding is None and not supporters:
            return ElementResult(element, Status.SKIP, reason="nothing supports it or checks it")
        if blocked_by := self._blocking(supporters):
            reason = f"not run: {', '.join(blocked_by)} did not pass"
            return ElementResult(element, Status.SKIP, binding, reason, blocked_by)
        return ElementResult(element, Status.PASS) if binding is None else binding

    def _take(self, position: int) -> None:
        """Decide the element at ``position``, whose supporters are all decided, or start
        its step."""
        element = self._order[position]
        settled = self._bound_at.pop(position, None) or self._settled(element)
        if isinstance(settled, ElementResult):
            self._decide(settled)
        else:
            binding = settled
            self._listener.element_started(element)
            arguments = {
                c.input.parameter: self._consumed(c) for c in self._dataflow.of(element.id)
            }
            context = Context(binding.step.directory, self._root)
            if self._jobs == 1:
                self._decide(self._tried(_attempt(binding, arguments, context, self._sighted)))
            else:
                self._running += 1
                # The step sees the context variables of the thread that runs the run, such
                # as decimal's context, as it would on that thread.
                thread = Thread(
                    target=copy_context().run,
                    args=(self._work, binding, arguments, context),
                    name=f"jpipe-runner-step {element.id}",
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()

    def _work(self, binding: Binding, arguments: dict[str, Any], context: Context) -> None:
        """What a step's thread does: try ``binding``'s step, and tell this run."""
        try:
            self._inbox.put(_attempt(binding, arguments, context, self._inbox.put))
        # Whatever escapes is the runner's bug, or a step that raised KeyboardInterrupt: the
        # thread that runs the run raises it again (_messages).
        except BaseException as error:  # NOSONAR
            self._inbox.put(error)

    def _messages(self) -> list["_Sighted | _Attempt"]:
        """The messages from the steps' threads: the next, and every other already sent.
        If one is an exception, it is raised before any is handled, so that a run stopped
        while another step ended starts no step in its place."""
        messages = [self._next()]
        while True:
            try:
                messages.append(self._inbox.get_nowait())
            except Empty:
                break
        for message in messages:
            if isinstance(message, BaseException):
                raise message
        return [message for message in messages if not isinstance(message, BaseException)]

    def _next(self) -> "_Sighted | _Attempt | BaseException":
        """The next message from a step's thread. The wait is cut short now and then, so
        that KeyboardInterrupt stops the run on every platform."""
        while True:
            try:
                return self._inbox.get(timeout=_WAKE_UP)
            except Empty:
                continue

    def _receive(self, message: "_Sighted | _Attempt") -> None:
        if isinstance(message, _Sighted):
            self._sighted(message)
        else:
            self._running -= 1
            self._decide(self._tried(message))

    def _sighted(self, sighted: "_Sighted") -> None:
        for source, reachable in sighted.observed.sources:
            self._listener.source_observed(sighted.element, source, reachable)

    def _decide(self, result: ElementResult) -> None:
        """Record ``result``, tell the listener, and make ready what it was the last
        undecided supporter of."""
        element = result.element
        if result.binding is not None:
            result = replace(result, inputs=self._dataflow.received(element.id))
        _LOG.info("%s %s: %s", result.status, element.id, result.reason or "")
        self._results[element.id] = result
        self._listener.element_decided(result)
        for supported in self._model.supported(element.id):
            self._undecided[supported.id] -= 1
            if not self._undecided[supported.id]:
                self._became_ready(supported)

    def _blocking(self, supporters: tuple[Element, ...]) -> tuple[str, ...]:
        """The elements that stop an element so supported: each supporter that did not
        pass on its own account, and what stopped those that were stopped."""
        roots: set[str] = set()
        for supporter in supporters:
            result = self._results[supporter.id]
            if result.status is not Status.PASS:
                roots.update(result.blocked_by or (supporter.id,))
        return tuple(element.id for element in self._model.in_model_order(roots))

    def _tried(self, attempt: "_Attempt") -> ElementResult:
        """The result of a step tried: failed if something could not be reached, if it
        raised, or if it returned anything but an outcome; otherwise, what it returned."""
        binding, observed = attempt.binding, attempt.observed
        observations = observed.observations
        if not observed.reachable:
            result = _failed(binding, observed.diagnostics, observed=observations, ran=False)
        elif attempt.raised is not None:
            error = attempt.raised
            raised = _raised(binding.element, error, user_traceback(error), self._root)
            result = _failed(binding, (raised,), observed=observations)
        else:
            try:
                outcome = as_outcome(attempt.returned, binding.element.id)
            except NotAnOutcomeError as error:
                result = _failed(binding, (error.diagnostic,), observed=observations)
            else:
                result = self._judged(binding, outcome, observations)
        # SonarCloud types dataclasses.replace as returning any dataclass (S5886); mypy
        # --strict checks that this is an ElementResult.
        return replace(result, reached=observed.sources)  # NOSONAR

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
            produced=MappingProxyType(
                {name: snapshot(v, self._root) for name, v in produced.items()}
            ),
            observed=observed,
            diagnostics=tuple(problems),
        )


@dataclass(frozen=True)
class _Sighted:
    """What a step's thread tells the run once it observed the artifacts of ``element``."""

    element: Element
    observed: Observed


@dataclass(frozen=True)
class _Attempt:
    """A bound element's step, tried: what it observed, then what it returned, or what it
    raised. Not called if something could not be reached."""

    binding: Binding
    observed: Observed
    returned: Any = None
    raised: Exception | SystemExit | None = None


def _attempt(
    binding: Binding,
    arguments: Mapping[str, Any],
    context: Context,
    sighted: Callable[[_Sighted], None],
) -> _Attempt:
    """Observe what ``binding``'s step observes, from ``context``, tell ``sighted``, then
    call the step with ``arguments`` and what it observed, if everything was reached. This
    is all a step's thread does: it reads no value, and records nothing."""
    element, step = binding.element, binding.step
    observed = observe(step.observes, context, element.id)
    sighted(_Sighted(element, observed))
    if not observed.reachable:
        return _Attempt(binding, observed)
    _LOG.debug("calling %s for %s", step.name, element.id)
    try:
        returned = step.function(**{**arguments, **observed.arguments})
    # A step that calls sys.exit() fails its element, rather than end the run without a
    # report; KeyboardInterrupt still stops it (ADR-0021).
    except (Exception, SystemExit) as error:  # NOSONAR
        return _Attempt(binding, observed, raised=error)
    return _Attempt(binding, observed, returned=returned)


def _failed(
    binding: Binding,
    diagnostics: Sequence[Diagnostic],
    *,
    observed: tuple[Observation, ...],
    outcome: Outcome | None = None,
    ran: bool = True,
) -> ElementResult:
    """The element failed because of ``diagnostics``: its step was called, unless ``ran``
    says it was not."""
    errors = [d.message for d in diagnostics if d.severity is Severity.ERROR]
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
