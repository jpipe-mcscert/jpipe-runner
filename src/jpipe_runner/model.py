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

from jpipe_runner.diagnostics import Diagnostic, Severity

DUPLICATE_ID = "JP002"
DANGLING_RELATION = "JP003"


class Kind(StrEnum):
    """An element's kind, valued as the compiler writes it."""

    EVIDENCE = "evidence"
    STRATEGY = "strategy"
    SUB_CONCLUSION = "sub-conclusion"
    CONCLUSION = "conclusion"


@dataclass(frozen=True)
class Element:
    id: str
    label: str
    kind: Kind
    aliases: tuple[str, ...] = ()
    """The ids of the elements that composition merged into this one (#115)."""

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


class InvalidJustificationError(Exception):
    """A model that cannot be run. It carries every problem found, as diagnostics."""

    def __init__(self, diagnostics: Iterable[Diagnostic]) -> None:
        self.diagnostics = tuple(diagnostics)
        super().__init__("\n".join(str(diagnostic) for diagnostic in self.diagnostics))


class Justification:
    """A justification model: its elements, and the directed graph their relations form.

    The graph is hidden (ADR-0016): ask the model for an element's supporters, the elements
    it supports, a topological order or a cycle. Results are deterministic, ordered by model
    order (the order in which the model lists its elements): supporters and supported
    elements are sorted by it, the topological order breaks ties by it, and a cycle starts
    from its element that comes first in it. A model does not change once loaded.

    Raises ``InvalidJustificationError`` if an id is declared twice (JP002) or a relation
    names an element that does not exist (JP003). Neither can be represented by the graph:
    it would merge the duplicates, and invent the missing element.
    """

    def __init__(self, name: str, elements: Iterable[Element], relations: Iterable[Relation]):
        self._name = name
        self._elements = tuple(elements)
        self._relations = tuple(relations)

        problems = [*_duplicate_ids(self._elements), *_dangling(self._relations, self._elements)]
        if problems:
            raise InvalidJustificationError(problems)

        self._by_id = {element.id: element for element in self._elements}
        self._rank = {element.id: rank for rank, element in enumerate(self._elements)}
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(self._by_id)
        graph.add_edges_from((relation.source, relation.target) for relation in self._relations)
        self._graph: nx.DiGraph[str] = nx.freeze(graph)

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

    def element(self, element_id: str) -> Element:
        """The element whose own id is ``element_id``. Aliases are not looked up here."""
        try:
            return self._by_id[element_id]
        except KeyError:
            raise KeyError(f"no element with id {element_id!r} in {self._name!r}") from None

    def supporters(self, element_id: str) -> tuple[Element, ...]:
        """The elements that directly support ``element_id``, in model order."""
        return self._in_model_order(self._graph.predecessors(self.element(element_id).id))

    def supported(self, element_id: str) -> tuple[Element, ...]:
        """The elements that ``element_id`` directly supports, in model order."""
        return self._in_model_order(self._graph.successors(self.element(element_id).id))

    def topological_order(self) -> tuple[Element, ...]:
        """Every element after all of its supporters, ties broken by model order.

        Raises ``ValueError`` if the graph has a cycle, which has no such order.
        """
        try:
            ordered = nx.lexicographical_topological_sort(self._graph, key=self._rank.__getitem__)
            return tuple(self._by_id[element_id] for element_id in ordered)
        except nx.NetworkXUnfeasible:
            raise ValueError(f"{self._name!r} has a cycle: {self.cycle()}") from None

    def cycle(self) -> tuple[str, ...] | None:
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

    def _in_model_order(self, element_ids: Iterable[str]) -> tuple[Element, ...]:
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
