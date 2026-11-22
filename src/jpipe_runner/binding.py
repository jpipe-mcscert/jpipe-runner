"""Binding: which step implements which element (ADR-0007).

A step names its elements by the ids given to its decorator. An id designates an element
by the first of these rules that matches:

1. **exact**: it is the element's id or one of its aliases;
2. **qualified**: it is ``<justification>:<id>``, and ``<id>`` matches exactly;
3. **suffix**: it is a strictly shorter tail of an element's id or alias, cut at ``:``
   boundaries, so ``e_metric`` and ``r17:e_metric`` designate ``rigor:r17:e_metric``, and
   ``metric`` and ``r17`` do not.

An exact match therefore always wins, and a suffix that designates two elements is
ambiguous rather than resolved to either. Elements carry several ids because composition
merges them: the compiler aliases every merged original onto the merged element, then
shortens the ids it writes into a step library to the least qualified form that still
designates one element. This rule resolves exactly those forms.

The compiler names each composed element's **origins** too: the element as it was in each
model it was composed from, by its full id there. An origin's id is always a tail of one of
the element's ids, so it designates the element by these rules. Which origin a step's id
designates, as the origin's id itself or a tail of it, tells validation the kind the step
was written for (ADR-0036). An id qualified by the composed model's name was written
against the composed model, so it designates no origin.

A ``BindingTable`` binds a registry's steps to a model's elements, one to one, and reports
every id that designates no element (JP015) or several (JP006), and every element or step
bound more than once (JP007).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from functools import cached_property

from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.model import Element, Justification, Origin
from jpipe_runner.steps import Step, StepRegistry

AMBIGUOUS_BINDING = "JP006"
CONFLICTING_BINDING = "JP007"
UNKNOWN_BINDING_TARGET = "JP015"


class AmbiguousIdError(LookupError):
    """An id that designates several elements, by suffix."""

    def __init__(self, designator: str, candidates: tuple[Element, ...]) -> None:
        self.designator = designator
        self.candidates = candidates
        ids = ", ".join(repr(element.id) for element in candidates)
        super().__init__(f"{designator!r} designates {len(candidates)} elements: {ids}")


class Resolver:
    """Resolves the ids a step library uses to the elements of one model."""

    def __init__(self, justification: Justification) -> None:
        self._name = justification.name
        # Every id and alias designates one element: the model refuses anything else (JP002).
        self._exact = {key: element for element in justification for key in element.ids}
        self._keys = [(key.split(":"), element) for key, element in self._exact.items()]

    def resolve(self, designator: str) -> Element | None:
        """The element ``designator`` designates, or ``None`` if it designates none.

        Raises ``AmbiguousIdError`` if it is a suffix of the ids of several elements.
        """
        if (element := self._exact.get(designator)) is not None:
            return element
        local = designator.removeprefix(f"{self._name}:")
        if local != designator and (element := self._exact.get(local)) is not None:
            return element
        wanted = designator.split(":")
        matches = {
            element.id: element for segments, element in self._keys if _tail(wanted, segments)
        }
        if len(matches) > 1:
            raise AmbiguousIdError(designator, tuple(matches.values()))
        return next(iter(matches.values()), None)


def _designates(designator: str, origin: str) -> bool:
    """Whether ``designator`` is the id ``origin``, or a tail of it, as a library written
    against the origin's model names it."""
    return designator == origin or _tail(designator.split(":"), origin.split(":"))


def _tail(wanted: list[str], segments: list[str]) -> bool:
    """Whether ``wanted`` is a strictly shorter tail of ``segments``."""
    return len(wanted) < len(segments) and segments[-len(wanted) :] == wanted


@dataclass(frozen=True)
class Binding:
    """An element, the step that implements it, and the step's ids that designate it."""

    element: Element
    step: Step
    designators: tuple[str, ...]

    @cached_property
    def origin(self) -> Origin | None:
        """The origin of the element that the step's ids designate, with the step's kind:
        the element as the step was written for it, before composition changed its kind.
        ``None`` if there is none (ADR-0036)."""
        return next(
            (
                origin
                for origin in self.element.origins
                if origin.kind is self.step.kind
                and any(_designates(d, origin.id) for d in self.designators)
            ),
            None,
        )


class BindingTable:
    """The steps of a registry bound to the elements of a model, one to one.

    Every problem is collected, not raised: ``diagnostics`` lists them in the registry's
    order, and an element or a step involved in a JP007 conflict is left unbound; the
    elements it concerns are ``contested``. ``bindings`` are in model order.
    """

    def __init__(self, justification: Justification, registry: StepRegistry) -> None:
        resolver = Resolver(justification)
        problems: list[Diagnostic] = []
        contested: set[str] = set()
        candidates: dict[str, list[Binding]] = {}
        for step in registry:
            binding = _bind(step, resolver, justification.name, problems, contested)
            if binding is not None:
                candidates.setdefault(binding.element.id, []).append(binding)

        bound: dict[str, Binding] = {}
        for element in justification:
            found = candidates.get(element.id, [])
            if len(found) == 1:
                bound[element.id] = found[0]
            elif found:
                contested.add(element.id)
                names = ", ".join(binding.step.name for binding in found)
                problems.append(
                    Diagnostic(
                        CONFLICTING_BINDING,
                        Severity.ERROR,
                        f"{element.id!r} is bound by {len(found)} functions: {names}",
                        element=element.id,
                        fix="Bind each element to one function: remove the others' ids for it.",
                    )
                )
        self._bound = bound
        self._diagnostics = tuple(problems)
        self._contested = frozenset(contested)
        self._resolver = resolver

    @property
    def resolver(self) -> Resolver:
        """What resolved the steps' ids, for any other id that designates an element."""
        return self._resolver

    @property
    def bindings(self) -> tuple[Binding, ...]:
        return tuple(self._bound.values())

    @property
    def diagnostics(self) -> tuple[Diagnostic, ...]:
        return self._diagnostics

    @property
    def contested(self) -> frozenset[str]:
        """The ids of the elements a JP007 conflict concerns: claimed by several steps, or
        designated by a step that designates several. None of them is bound."""
        return self._contested

    def binding_for(self, element_id: str) -> Binding | None:
        """The binding of the element whose own id is ``element_id``, if it is bound."""
        return self._bound.get(element_id)

    def step_for(self, element_id: str) -> Step | None:
        """The step bound to the element whose own id is ``element_id``, if any."""
        binding = self.binding_for(element_id)
        return None if binding is None else binding.step

    def __iter__(self) -> Iterator[Binding]:
        return iter(self._bound.values())

    def __len__(self) -> int:
        return len(self._bound)

    def __repr__(self) -> str:
        return f"BindingTable({len(self._bound)} bindings, {len(self._diagnostics)} problems)"


def _bind(
    step: Step, resolver: Resolver, model: str, problems: list[Diagnostic], contested: set[str]
) -> Binding | None:
    """The element all of ``step``'s ids designate, or ``None`` after reporting why not.

    The elements of a step whose ids designate several are added to ``contested``.
    """
    targets: dict[str, list[str]] = {}
    elements: dict[str, Element] = {}
    for designator in step.ids:
        try:
            element = resolver.resolve(designator)
        except AmbiguousIdError as error:
            problems.append(
                Diagnostic(
                    AMBIGUOUS_BINDING,
                    Severity.ERROR,
                    f"{step.name}: {error}",
                    fix="Use a longer, more qualified id, which designates one element.",
                )
            )
            continue
        if element is None:
            problems.append(
                Diagnostic(
                    UNKNOWN_BINDING_TARGET,
                    Severity.ERROR,
                    f"{step.name}: {designator!r} designates no element of {model!r}, "
                    f"so the function would never run",
                    fix="Use the id of an element of the model, as the compiler exports it.",
                )
            )
            continue
        targets.setdefault(element.id, []).append(designator)
        elements[element.id] = element
    if len(targets) > 1:
        contested.update(targets)
        ids = ", ".join(map(repr, targets))
        problems.append(
            Diagnostic(
                CONFLICTING_BINDING,
                Severity.ERROR,
                f"{step.name}: its ids designate {len(targets)} elements: {ids}",
                fix="Bind a function to one element: write one function per element.",
            )
        )
        return None
    if not targets:
        return None
    ((element_id, designators),) = targets.items()
    return Binding(elements[element_id], step, tuple(designators))
