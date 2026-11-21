"""Dataflow: which step each value a step consumes comes from (ADR-0031).

A step receives a value only from its supporters, direct or not: it runs after them, and
is skipped when one of them does not pass (ADR-0021). So a consumed variable is resolved
among the consumer's supporters, not across the model. Its **candidates** are the bound
steps that produce it and support the consumer, narrowed, when the input names one with
``Produced(variable, by=id)``, to those at or below the element ``by`` designates. There
must be exactly one. Two steps may therefore produce the same variable, as libraries
written apart do, as long as no consumer can see both.

A ``DataflowTable`` resolves every input of every bound step once, after binding. It is
what the rules check (JP009, JP011 to JP014, JP025), what the engine passes to each step,
and what the report says each step received. An id given as ``by`` designates an element
as a step's own ids do (ADR-0007): one that designates no element is JP015, one that
designates several is JP006.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from jpipe_runner.binding import (
    AMBIGUOUS_BINDING,
    UNKNOWN_BINDING_TARGET,
    AmbiguousIdError,
    Binding,
    BindingTable,
    Resolver,
)
from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.model import Element, Justification
from jpipe_runner.steps import Input


@dataclass(frozen=True)
class Consumption:
    """One input of a bound step, and the steps that could provide it."""

    consumer: Binding
    input: Input
    within: Element | None
    """The element ``input.by`` designates, or ``None`` when it has none, or designates
    no element or several."""
    designated: bool
    """Whether ``input.by``, if given, designates one element."""
    producers: tuple[Binding, ...]
    """Every bound step that produces the variable, in model order."""
    reachable: tuple[Binding, ...]
    """Those of ``producers`` at or below ``within``: all of them when there is no ``by``."""
    candidates: tuple[Binding, ...]
    """Those of ``reachable`` that support the consumer, directly or not."""

    @property
    def producer(self) -> Binding | None:
        """The step the value comes from: the only candidate, if there is exactly one."""
        return self.candidates[0] if len(self.candidates) == 1 else None

    @property
    def sources(self) -> tuple[Binding, ...]:
        """The steps it draws on: its candidates, or, when none supports the consumer, the
        producers it names, which validation reports (JP014)."""
        return self.candidates or self.reachable


@dataclass(frozen=True)
class Received:
    """What a parameter of a step receives: a variable, and the id of the element whose
    step produced it, or ``None`` if it does not resolve to one."""

    parameter: str
    variable: str
    produced_by: str | None


class DataflowTable:
    """Every input of every bound step, resolved among the step's supporters.

    ``consumptions`` are in model order of their consumers, then in the order of each
    step's inputs. ``diagnostics`` are the ids given as ``by`` that designate no element
    (JP015) or several (JP006).
    """

    def __init__(self, justification: Justification, bindings: BindingTable) -> None:
        resolver = Resolver(justification)
        upstream = {e.id: {u.id for u in justification.upstream(e.id)} for e in justification}
        producers: dict[str, list[Binding]] = {}
        for binding in bindings:
            for variable in binding.step.produces:
                producers.setdefault(variable, []).append(binding)
        problems: list[Diagnostic] = []
        found: list[Consumption] = []
        for consumer in bindings:
            for each in consumer.step.inputs:
                within, designated = _designated(consumer, each, resolver, problems)
                every = tuple(producers.get(each.variable, ()))
                region = None if within is None else {within.id} | upstream[within.id]
                reachable = tuple(
                    p for p in every if designated and (region is None or p.element.id in region)
                )
                supporting = upstream[consumer.element.id]
                candidates = tuple(p for p in reachable if p.element.id in supporting)
                found.append(
                    Consumption(consumer, each, within, designated, every, reachable, candidates)
                )
        self._consumptions = tuple(found)
        self._diagnostics = tuple(problems)

    @property
    def consumptions(self) -> tuple[Consumption, ...]:
        return self._consumptions

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        return self._diagnostics

    def of(self, element_id: str) -> tuple[Consumption, ...]:
        """The inputs of the step bound to the element whose own id is ``element_id``."""
        return tuple(c for c in self._consumptions if c.consumer.element.id == element_id)

    def users(self, producer_id: str, variable: str) -> tuple[Consumption, ...]:
        """The inputs that draw on ``variable`` as the element ``producer_id`` produces it."""
        return tuple(
            c
            for c in self._consumptions
            if c.input.variable == variable and any(p.element.id == producer_id for p in c.sources)
        )

    def received(self, element_id: str) -> tuple[Received, ...]:
        """What each parameter of the step bound to ``element_id`` receives."""
        return tuple(
            Received(
                c.input.parameter,
                c.input.variable,
                None if c.producer is None else c.producer.element.id,
            )
            for c in self.of(element_id)
        )

    def __iter__(self) -> Iterator[Consumption]:
        return iter(self._consumptions)

    def __len__(self) -> int:
        return len(self._consumptions)

    def __repr__(self) -> str:
        return f"DataflowTable({len(self._consumptions)} inputs)"


def _designated(
    consumer: Binding, wanted: Input, resolver: Resolver, problems: list[Diagnostic]
) -> tuple[Element | None, bool]:
    """The element ``wanted.by`` designates, and whether it designates one: ``(None,
    True)`` when it has no ``by``. A ``by`` that designates none or several is reported."""
    if wanted.by is None:
        return None, True
    step, element = consumer.step, consumer.element.id
    try:
        within = resolver.resolve(wanted.by)
    except AmbiguousIdError as error:
        problems.append(
            Diagnostic(
                AMBIGUOUS_BINDING,
                Severity.ERROR,
                f"{step.name}: {wanted.by!r}, which names the producer of "
                f"{wanted.variable!r} it consumes, designates {len(error.candidates)} "
                f"elements: {', '.join(repr(e.id) for e in error.candidates)}",
                element=element,
                fix="Use a longer, more qualified id in by=..., which designates one element.",
            )
        )
        return None, False
    if within is None:
        problems.append(
            Diagnostic(
                UNKNOWN_BINDING_TARGET,
                Severity.ERROR,
                f"{step.name}: {wanted.by!r}, which names the producer of "
                f"{wanted.variable!r} it consumes, designates no element of "
                f"{resolver.name!r}",
                element=element,
                fix="Name an element of the model in by=..., as the compiler exports its id.",
            )
        )
        return None, False
    return within, True
