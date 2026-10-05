"""The generator's own invariants, so property tests built on it can trust its output."""

from collections import Counter
from typing import Any

import networkx as nx
from hypothesis import given

from tests.strategies import CLAIMS, CONCLUSION, KINDS, STRATEGY, SUPPORTS, justifications


def graph_of(model: dict[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for element in model["elements"]:
        graph.add_node(element["id"], kind=element["type"])
    for relation in model["relations"]:
        graph.add_edge(relation["source"], relation["target"])
    return graph


@given(justifications())
def test_ids_and_aliases_are_unique_and_qualified(model: dict[str, Any]) -> None:
    names = [e["id"] for e in model["elements"]]
    names += [alias for e in model["elements"] for alias in e.get("aliases", [])]
    assert len(names) == len(set(names))
    assert all(name.startswith(f"{model['name']}:") for name in names)


@given(justifications())
def test_relations_connect_existing_elements_once(model: dict[str, Any]) -> None:
    ids = {e["id"] for e in model["elements"]}
    edges = [(r["source"], r["target"]) for r in model["relations"]]
    assert all(source in ids and target in ids for source, target in edges)
    assert len(edges) == len(set(edges))


@given(justifications())
def test_structure_follows_jpipe_rules(model: dict[str, Any]) -> None:
    graph = graph_of(model)
    kinds = nx.get_node_attributes(graph, "kind")
    assert set(kinds.values()) <= set(KINDS)
    assert nx.is_directed_acyclic_graph(graph)

    (conclusion,) = [n for n, kind in kinds.items() if kind == CONCLUSION]
    assert [n for n in graph if graph.out_degree(n) == 0] == [conclusion]
    assert nx.ancestors(graph, conclusion) == set(graph) - {conclusion}

    for source, target in graph.edges:
        assert kinds[target] in SUPPORTS[kinds[source]]
    for node, kind in kinds.items():
        if kind in CLAIMS:
            assert [kinds[p] for p in graph.predecessors(node)] == [STRATEGY]
        if kind == STRATEGY:
            assert graph.out_degree(node) == 1
            assert graph.in_degree(node) >= 1


@given(justifications(aliases=False))
def test_aliases_can_be_turned_off(model: dict[str, Any]) -> None:
    assert not any("aliases" in e for e in model["elements"])


@given(justifications())
def test_escaped_is_all_or_nothing(model: dict[str, Any]) -> None:
    assert len(Counter("escaped" in e for e in model["elements"])) == 1
