"""Dataflow: which step each value a step consumes comes from (ADR-0031).

A step receives a value only from its supporters, direct or not: it runs after them, and
is skipped when one of them does not pass (ADR-0021). So a consumed variable is resolved
among the consumer's supporters, not across the model. Its **candidates** are the bound
steps that produce it and support the consumer, narrowed, when the input names one with
``Produced(variable, by=id)``, to the step of the element ``by`` designates, if that step
produces the variable, and otherwise to those below it. There must be exactly one. Two
steps may therefore produce the same variable, as libraries written apart do, as long as
no consumer can see both, and a step that sees both names the one it means.

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
    producers: tuple[Binding, ...]
    """Every bound step that produces the variable, in model order."""
    reachable: tuple[Binding, ...]
    """Those of ``producers`` that ``by`` names: the step of ``within`` if it is one of
    them, else those below ``within``; all of them when there is no ``by``."""
    candidates: tuple[Binding, ...]
    """Those of ``reachable`` that support the consumer, directly or not."""

    @property
    def designated(self) -> bool:
        """Whether ``input.by``, if given, designates one element."""
        return self.input.by is None or self.within is not None

    @property
    def producer(self) -> Binding | None:
        """The step the value comes from: the only candidate, if there is exactly one."""
        return self.candidates[0] if len(self.candidates) == 1 else None

    @property
    def sources(self) -> tuple[Binding, ...]:
        """The steps it draws on: its candidates, or, when none supports the consumer, the
        producers it names, or when it names none, every producer of its variable. The
        mistake is then reported on the consumer (JP014, JP015, JP006), not again on each
        producer as an unconsumed value (JP011, JP012)."""
        return self.candidates or self.reachable or self.producers


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
        self._justification = justification
        self._upstream: dict[str, frozenset[str]] = {}
        producers: dict[str, list[Binding]] = {}
        for binding in bindings:
            for variable in binding.step.produces:
                producers.setdefault(variable, []).append(binding)
        problems: list[Diagnostic] = []
        self._consumptions = tuple(
            self._resolved(consumer, each, producers, bindings, problems)
            for consumer in bindings
            for each in consumer.step.inputs
        )
        self._diagnostics = tuple(problems)
        self._by_consumer: dict[str, list[Consumption]] = {}
        self._by_source: dict[tuple[str, str], list[Consumption]] = {}
        for consumed in self._consumptions:
            self._by_consumer.setdefault(consumed.consumer.element.id, []).append(consumed)
            for source in consumed.sources:
                key = (source.element.id, consumed.input.variable)
                self._by_source.setdefault(key, []).append(consumed)

    def _resolved(
        self,
        consumer: Binding,
        wanted: Input,
        producers: dict[str, list[Binding]],
        bindings: BindingTable,
        problems: list[Diagnostic],
    ) -> Consumption:
        """``wanted``, an input of ``consumer``, with the steps that could provide it."""
        within = _designated(consumer, wanted, bindings, self._justification.name, problems)
        every = tuple(producers.get(wanted.variable, ()))
        if within is not None:
            reachable = self._named(within, every)
        else:
            reachable = () if wanted.by is not None else every
        supporting = self._supporters(consumer.element.id)
        candidates = tuple(p for p in reachable if p.element.id in supporting)
        return Consumption(consumer, wanted, within, every, reachable, candidates)

    def _supporters(self, element_id: str) -> frozenset[str]:
        """The ids of the elements that support ``element_id``, directly or not."""
        if element_id not in self._upstream:
            found = self._justification.upstream(element_id)
            self._upstream[element_id] = frozenset(e.id for e in found)
        return self._upstream[element_id]

    def _named(self, within: Element, producers: tuple[Binding, ...]) -> tuple[Binding, ...]:
        """The producers ``by`` names when it designates ``within``: its own step, if it is
        one of them, so that a producer can be named even above another producer of the
        same variable; else every one below it."""
        if own := tuple(p for p in producers if p.element.id == within.id):
            return own
        below = self._supporters(within.id)
        return tuple(p for p in producers if p.element.id in below)

    @property
    def consumptions(self) -> tuple[Consumption, ...]:
        return self._consumptions

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        return self._diagnostics

    def of(self, element_id: str) -> tuple[Consumption, ...]:
        """The inputs of the step bound to the element whose own id is ``element_id``."""
        return tuple(self._by_consumer.get(element_id, ()))

    def users(self, producer_id: str, variable: str) -> tuple[Consumption, ...]:
        """The inputs that draw on ``variable`` as the element ``producer_id`` produces it."""
        return tuple(self._by_source.get((producer_id, variable), ()))

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
    consumer: Binding, wanted: Input, bindings: BindingTable, model: str, problems: list[Diagnostic]
) -> Element | None:
    """The element ``wanted.by`` designates, or ``None`` when it has no ``by``, or one
    that designates no element or several, which is reported."""
    if wanted.by is None:
        return None
    step, element = consumer.step, consumer.element.id
    try:
        within = bindings.resolver.resolve(wanted.by)
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
        return None
    if within is None:
        problems.append(
            Diagnostic(
                UNKNOWN_BINDING_TARGET,
                Severity.ERROR,
                f"{step.name}: {wanted.by!r}, which names the producer of "
                f"{wanted.variable!r} it consumes, designates no element of {model!r}",
                element=element,
                fix="Name an element of the model in by=..., as the compiler exports its id.",
            )
        )
    return within
