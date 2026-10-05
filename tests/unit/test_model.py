import networkx as nx
import pytest

from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.model import Element, InvalidJustificationError, Justification, Kind, Relation

EVIDENCE = Element("m:e", "The tests pass", Kind.EVIDENCE)
STRATEGY = Element("m:s", "Check the tests", Kind.STRATEGY, aliases=("a:s", "b:s"))
CONCLUSION = Element("m:c", "The code is tested", Kind.CONCLUSION)
RELATIONS = (Relation("m:e", "m:s"), Relation("m:s", "m:c"))


def model(
    elements: tuple[Element, ...] = (CONCLUSION, STRATEGY, EVIDENCE),
    relations: tuple[Relation, ...] = RELATIONS,
) -> Justification:
    return Justification("m", elements, relations)


def test_kinds_are_valued_as_the_compiler_writes_them() -> None:
    assert [kind.value for kind in Kind] == [
        "evidence",
        "strategy",
        "sub-conclusion",
        "conclusion",
    ]


def test_an_element_is_designated_by_its_id_then_its_aliases() -> None:
    assert STRATEGY.ids == ("m:s", "a:s", "b:s")
    assert EVIDENCE.ids == ("m:e",)


def test_elements_and_relations_keep_the_model_order() -> None:
    justification = model()
    assert justification.name == "m"
    assert justification.elements == (CONCLUSION, STRATEGY, EVIDENCE)
    assert list(justification) == [CONCLUSION, STRATEGY, EVIDENCE]
    assert justification.relations == RELATIONS
    assert len(justification) == 3
    assert repr(justification) == "Justification('m', 3 elements, 2 relations)"


def test_the_graph_goes_from_supporter_to_supported() -> None:
    graph = model().graph
    assert set(graph.edges) == {("m:e", "m:s"), ("m:s", "m:c")}
    assert list(nx.topological_sort(graph)) == ["m:e", "m:s", "m:c"]
    assert graph.nodes["m:s"]["element"] is STRATEGY
    assert graph.graph["name"] == "m"


def test_the_graph_is_frozen() -> None:
    with pytest.raises(nx.NetworkXError):
        model().graph.add_node("m:x")


def test_elements_are_looked_up_by_their_own_id() -> None:
    justification = model()
    assert justification.element("m:s") is STRATEGY
    assert "m:s" in justification
    assert "a:s" not in justification  # aliases are resolved by binding (#115), not here
    with pytest.raises(KeyError, match="m:x"):
        justification.element("m:x")


def test_a_cycle_is_left_to_validation() -> None:
    cyclic = model(relations=(*RELATIONS, Relation("m:c", "m:e")))
    assert not nx.is_directed_acyclic_graph(cyclic.graph)


def codes(error: pytest.ExceptionInfo[InvalidJustificationError]) -> list[tuple[str, str | None]]:
    assert all(d.severity is Severity.ERROR for d in error.value.diagnostics)
    return [(d.code, d.element) for d in error.value.diagnostics]


def test_a_duplicate_id_is_reported_once_per_id() -> None:
    twin = Element("m:e", "Another label", Kind.EVIDENCE)
    with pytest.raises(InvalidJustificationError) as error:
        model(elements=(CONCLUSION, STRATEGY, EVIDENCE, twin, twin))
    assert codes(error) == [("JP002", "m:e")]


@pytest.mark.parametrize(
    "relation",
    [
        pytest.param(Relation("m:x", "m:s"), id="source"),
        pytest.param(Relation("m:e", "m:x"), id="target"),
        pytest.param(Relation("m:x", "m:y"), id="both"),
    ],
)
def test_a_relation_to_an_unknown_element_is_reported(relation: Relation) -> None:
    with pytest.raises(InvalidJustificationError) as error:
        model(relations=(*RELATIONS, relation))
    assert codes(error) == [("JP003", None)]


def test_every_structural_problem_is_reported_together() -> None:
    with pytest.raises(InvalidJustificationError) as error:
        model(
            elements=(CONCLUSION, STRATEGY, EVIDENCE, EVIDENCE, STRATEGY),
            relations=(Relation("m:x", "m:c"), Relation("m:e", "m:y")),
        )
    assert codes(error) == [("JP002", "m:s"), ("JP002", "m:e"), ("JP003", None), ("JP003", None)]


def test_the_error_message_lists_the_diagnostics() -> None:
    problems = [
        Diagnostic("JP002", Severity.ERROR, "first", element="m:e"),
        Diagnostic("JP003", Severity.ERROR, "second"),
    ]
    assert str(InvalidJustificationError(problems)) == (
        "JP002 error [m:e]: first\nJP003 error: second"
    )
