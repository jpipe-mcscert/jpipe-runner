"""The justification model: elements, the relations between them, and the graph they form.

A model comes from the jPipe compiler (ADR-0001) and is read by ``jpipe_runner.loader``.
A relation goes from the supporting element to the element it supports, so evidence are
sources and the conclusion is the sink.

The graph is a NetworkX ``DiGraph`` private to ``Justification``, which answers questions
about it in the model's terms (ADR-0016). No NetworkX type crosses the public API.
"""

from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum

import networkx as nx

from jpipe_runner.diagnostics import Diagnostic, DiagnosticsError, Severity

DUPLICATE_ID = "JP002"
DANGLING_RELATION = "JP003"
CYCLE = "JP004"


class Kind(StrEnum):
    """An element's kind, valued as the compiler writes it."""

    EVIDENCE = "evidence"
    STRATEGY = "strategy"
    SUB_CONCLUSION = "sub-conclusion"
    CONCLUSION = "conclusion"

    @property
    def decorator(self) -> str:
        """The decorator that declares a step of this kind: ``@sub_conclusion``."""
        return f"@{self.value.replace('-', '_')}"


@dataclass(frozen=True)
class Origin:
    """An element as it was in a model that composition built this one from (jPipe 4.0.0)."""

    model: str
    """The name of that model."""
    id: str
    """The element's full id there, as the compiler exports that model."""
    kind: Kind
    """The element's kind there, which composition may have changed (ADR-0036)."""


@dataclass(frozen=True)
class Element:
    id: str
    label: str
    kind: Kind
    aliases: tuple[str, ...] = ()
    """The ids of the elements that composition merged into this one (#115)."""
    origins: tuple[Origin, ...] = ()
    """The element in each model it was composed from, nearest first. Empty in a model that
    was not composed, and in one composed by a compiler older than jPipe 4.0.0."""

    @property
    def ids(self) -> tuple[str, ...]:
        """Every id that designates this element: its own, then its aliases."""
        return (self.id, *self.aliases)


@dataclass(frozen=True)
class Relation:
    source: str
    """The supporting element."""
    target: str
    """The element it supports."""


@dataclass(frozen=True)
class Placeholder:
    """A template's ``@support`` that an element further down the chain fills.

    It is drawn in its template, with its own label, and linked to the element that fills
    it, which has the same id.
    """

    id: str
    """The id of the element that fills it."""
    label: str
    supports: tuple[str, ...] = ()
    """The strategies whose support by ``id`` is drawn from the placeholder: the edge
    belongs to the template."""


@dataclass(frozen=True)
class Template:
    """A template of the chain a justification implements, as the compiler draws it."""

    name: str
    elements: tuple[str, ...]
    """The ids drawn in the template, in drawing order: its own elements, then the
    ``@support``s it fills further up. The id of one of its ``placeholders`` stands for the
    placeholder."""
    placeholders: tuple[Placeholder, ...] = ()


@dataclass(frozen=True)
class TemplateChain:
    """How the compiler draws a justification that implements a template (jPipe 4.0.0).

    The run does not depend on it: the model's elements and relations are the template's
    and the justification's, flattened. Only the diagram uses it.
    """

    elements: tuple[str, ...]
    """The ids drawn outside every template, in drawing order: the justification's own
    elements, then the ``@support``s it fills."""
    templates: tuple[Template, ...]
    """The chain, the template the justification implements first. Each is drawn inside
    the one before it."""

    @property
    def ids(self) -> tuple[str, ...]:
        """Every element id the chain names, once each, in the order it first names them.

        The compiler lists a placeholder's id among its template's elements too, but a
        placeholder is still read for its id: the chain is checked against the model
        without relying on how the compiler lays it out (#179).
        """
        return tuple(
            dict.fromkeys(
                (
                    *self.elements,
                    *(i for template in self.templates for i in template.elements),
                    *(
                        i
                        for template in self.templates
                        for placeholder in template.placeholders
                        for i in (placeholder.id, *placeholder.supports)
                    ),
                )
            )
        )


class InvalidJustificationError(DiagnosticsError):
    """A model that cannot be run. It carries every problem found, as diagnostics."""


class Justification:
    """A justification model: its elements, and the directed graph their relations form.

    The graph is hidden (ADR-0016): ask the model for an element's supporters, the elements
    it supports, those upstream of it, or a topological order. Results are deterministic,
    ordered by model order (the order in which the model lists its elements): supporters,
    supported and upstream elements are sorted by it, and the topological order breaks ties
    by it. A model does not change once loaded.

    Raises ``InvalidJustificationError`` if an id is declared twice or designates two
    elements, as an id or an alias (JP002), or if a relation names an element that does not
    exist (JP003). The graph can represent neither: it would merge the duplicates, and
    invent the missing element. Binding resolution needs an id or alias to designate one
    element (#115). It also raises if the relations form a cycle (JP004), which the
    compiler never emits: an argument cannot support itself, and its steps would have no
    order to run in (ADR-0010).

    A ``template_chain`` that names an element that does not exist is not kept: only the
    diagram reads it, which then draws the argument flat, and the run does not depend on
    it. Its unknown ids are kept instead, for validation to warn about (JP026, #177).
    """

    def __init__(
        self,
        name: str,
        elements: Iterable[Element],
        relations: Iterable[Relation],
        template_chain: TemplateChain | None = None,
    ):
        self._name = name
        self._elements = tuple(elements)
        self._relations = tuple(relations)
        self._unknown_in_template_chain = _unknown_in_chain(template_chain, self._elements)
        self._template_chain = None if self._unknown_in_template_chain else template_chain

        problems = [
            *_duplicate_ids(self._elements),
            *_shared_aliases(self._elements),
            *_dangling(self._relations, self._elements),
        ]
        if problems:
            raise InvalidJustificationError(problems)

        self._by_id = {element.id: element for element in self._elements}
        self._rank = {element.id: rank for rank, element in enumerate(self._elements)}
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(self._by_id)
        graph.add_edges_from((relation.source, relation.target) for relation in self._relations)
        self._graph: nx.DiGraph[str] = nx.freeze(graph)
        if (cycle := self._cycle()) is not None:
            raise InvalidJustificationError([_cyclic(cycle)])

    @property
    def name(self) -> str:
        return self._name

    @property
    def elements(self) -> tuple[Element, ...]:
        """The elements, in the order the model lists them."""
        return self._elements

    @property
    def relations(self) -> tuple[Relation, ...]:
        """The relations, in the order the model lists them."""
        return self._relations

    @property
    def template_chain(self) -> TemplateChain | None:
        """How the compiler draws the templates this justification implements, or ``None``
        if it implements none, was compiled by a jPipe older than 4.0.0, or its chain names
        an element it does not have."""
        return self._template_chain

    @property
    def unknown_in_template_chain(self) -> tuple[str, ...]:
        """The ids the compiler's template chain names that are not elements, in the order
        the chain names them. If there is one, the chain was not kept."""
        return self._unknown_in_template_chain

    def element(self, element_id: str) -> Element:
        """The element whose own id is ``element_id``. Aliases are not looked up here."""
        try:
            return self._by_id[element_id]
        except KeyError:
            raise KeyError(f"no element with id {element_id!r} in {self._name!r}") from None

    def supporters(self, element_id: str) -> tuple[Element, ...]:
        """The elements that directly support ``element_id``, in model order."""
        return self.in_model_order(self._graph.predecessors(self.element(element_id).id))

    def supported(self, element_id: str) -> tuple[Element, ...]:
        """The elements that ``element_id`` directly supports, in model order."""
        return self.in_model_order(self._graph.successors(self.element(element_id).id))

    def upstream(self, element_id: str) -> tuple[Element, ...]:
        """The elements that support ``element_id``, directly or not, in model order."""
        return self.in_model_order(nx.ancestors(self._graph, self.element(element_id).id))

    def topological_order(self) -> tuple[Element, ...]:
        """Every element after all of its supporters, ties broken by model order."""
        ordered = nx.lexicographical_topological_sort(self._graph, key=self._rank.__getitem__)
        return tuple(self._by_id[element_id] for element_id in ordered)

    def _cycle(self) -> tuple[str, ...] | None:
        """The ids of the elements along one cycle of the graph, or ``None`` if it has none.

        Each element supports the next, and the last one supports the first. The cycle is
        listed in that direction, starting from its element that comes first in model order.
        """
        try:
            edges = nx.find_cycle(self._graph)
        except nx.NetworkXNoCycle:
            return None
        cycle = [edge[0] for edge in edges]
        start = cycle.index(min(cycle, key=self._rank.__getitem__))
        return (*cycle[start:], *cycle[:start])

    def in_model_order(self, element_ids: Iterable[str]) -> tuple[Element, ...]:
        """The elements whose ids are ``element_ids``, in model order."""
        return tuple(self._by_id[i] for i in sorted(element_ids, key=self._rank.__getitem__))

    def __contains__(self, element_id: object) -> bool:
        return isinstance(element_id, str) and element_id in self._by_id

    def __len__(self) -> int:
        return len(self._elements)

    def __iter__(self) -> Iterator[Element]:
        return iter(self._elements)

    def __repr__(self) -> str:
        return (
            f"Justification({self._name!r}, {len(self._elements)} elements, "
            f"{len(self._relations)} relations)"
        )


def _duplicate_ids(elements: tuple[Element, ...]) -> Iterator[Diagnostic]:
    counts = Counter(element.id for element in elements)
    for element_id, count in counts.items():
        if count > 1:
            yield Diagnostic(
                DUPLICATE_ID,
                Severity.ERROR,
                f"element id {element_id!r} is declared {count} times",
                element=element_id,
            )


def _shared_aliases(elements: tuple[Element, ...]) -> Iterator[Diagnostic]:
    """An id or alias that designates several elements, at least once as an alias."""
    owners: dict[str, dict[str, None]] = {}
    for element in elements:
        for key in element.ids:
            owners.setdefault(key, {})[element.id] = None
    for key, designated in owners.items():
        if len(designated) > 1:
            names = ", ".join(map(repr, designated))
            yield Diagnostic(
                DUPLICATE_ID,
                Severity.ERROR,
                f"{key!r} designates {len(designated)} elements, as an id or an alias: {names}",
                element=next(iter(designated)),
            )


def _dangling(
    relations: tuple[Relation, ...], elements: tuple[Element, ...]
) -> Iterator[Diagnostic]:
    ids = {element.id for element in elements}
    for relation in relations:
        missing = [end for end in (relation.source, relation.target) if end not in ids]
        if missing:
            names = " and ".join(repr(end) for end in missing)
            yield Diagnostic(
                DANGLING_RELATION,
                Severity.ERROR,
                f"relation {relation.source!r} -> {relation.target!r} names {names}, "
                f"which {'is not an element' if len(missing) == 1 else 'are not elements'}",
            )


def _unknown_in_chain(
    chain: TemplateChain | None, elements: tuple[Element, ...]
) -> tuple[str, ...]:
    if chain is None:
        return ()
    ids = {element.id for element in elements}
    return tuple(i for i in chain.ids if i not in ids)


def _cyclic(cycle: tuple[str, ...]) -> Diagnostic:
    path = " -> ".join(map(repr, (*cycle, cycle[0])))
    return Diagnostic(
        CYCLE,
        Severity.ERROR,
        f"the relations form a cycle: {path}",
        element=cycle[0],
        fix="An element cannot support itself, even indirectly: remove one of these relations.",
    )
