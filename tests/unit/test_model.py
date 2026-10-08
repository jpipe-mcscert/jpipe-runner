import pytest

from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.model import Element, InvalidJustificationError, Justification, Kind, Relation

EVIDENCE = Element("m:e", "The tests pass", Kind.EVIDENCE)
OTHER_EVIDENCE = Element("m:o", "The linter passes", Kind.EVIDENCE)
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


def test_relations_go_from_supporter_to_supported() -> None:
    justification = model()
    assert justification.supporters("m:s") == (EVIDENCE,)
    assert justification.supported("m:s") == (CONCLUSION,)
    assert justification.supporters("m:e") == ()
    assert justification.supported("m:c") == ()


def test_supporters_come_in_model_order_not_relation_order() -> None:
    justification = model(
        elements=(CONCLUSION, OTHER_EVIDENCE, STRATEGY, EVIDENCE),
        relations=(*RELATIONS, Relation("m:o", "m:s")),
    )
    assert justification.supporters("m:s") == (OTHER_EVIDENCE, EVIDENCE)


def test_the_topological_order_breaks_ties_by_model_order() -> None:
    assert model().topological_order() == (EVIDENCE, STRATEGY, CONCLUSION)
    justification = model(
        elements=(CONCLUSION, OTHER_EVIDENCE, STRATEGY, EVIDENCE),
        relations=(*RELATIONS, Relation("m:o", "m:s")),
    )
    assert justification.topological_order() == (OTHER_EVIDENCE, EVIDENCE, STRATEGY, CONCLUSION)


@pytest.mark.parametrize("query", ["element", "supporters", "supported"])
def test_an_unknown_id_is_a_key_error(query: str) -> None:
    lookup = getattr(model(), query)
    with pytest.raises(KeyError, match="m:x"):
        lookup("m:x")


def test_elements_are_looked_up_by_their_own_id() -> None:
    justification = model()
    assert justification.element("m:s") is STRATEGY
    assert "m:s" in justification
    assert "a:s" not in justification  # aliases are resolved by binding (#115), not here
    assert 1 not in justification
    assert ["m:s"] not in justification


def test_upstream_elements_support_directly_or_not_in_model_order() -> None:
    justification = model(
        elements=(CONCLUSION, OTHER_EVIDENCE, STRATEGY, EVIDENCE),
        relations=(*RELATIONS, Relation("m:o", "m:s")),
    )
    assert justification.upstream("m:c") == (OTHER_EVIDENCE, STRATEGY, EVIDENCE)
    assert justification.upstream("m:s") == (OTHER_EVIDENCE, EVIDENCE)
    assert justification.upstream("m:e") == ()


@pytest.mark.parametrize(
    ("elements", "cycle"),
    [
        pytest.param((CONCLUSION, STRATEGY, EVIDENCE), "'m:c' -> 'm:e' -> 'm:s' -> 'm:c'", id="c"),
        pytest.param((EVIDENCE, STRATEGY, CONCLUSION), "'m:e' -> 'm:s' -> 'm:c' -> 'm:e'", id="e"),
        pytest.param((STRATEGY, CONCLUSION, EVIDENCE), "'m:s' -> 'm:c' -> 'm:e' -> 'm:s'", id="s"),
    ],
)
def test_a_cycle_is_reported_from_supporter_to_supported_from_the_first_in_model_order(
    elements: tuple[Element, ...], cycle: str
) -> None:
    with pytest.raises(InvalidJustificationError) as error:
        model(elements=elements, relations=(*RELATIONS, Relation("m:c", "m:e")))
    assert codes(error) == [("JP004", elements[0].id)]
    assert cycle in error.value.diagnostics[0].message
    assert error.value.diagnostics[0].fix


def test_an_element_supporting_itself_is_a_cycle() -> None:
    with pytest.raises(InvalidJustificationError) as error:
        model(relations=(*RELATIONS, Relation("m:e", "m:e")))
    assert codes(error) == [("JP004", "m:e")]


def codes(error: pytest.ExceptionInfo[InvalidJustificationError]) -> list[tuple[str, str | None]]:
    assert all(d.severity is Severity.ERROR for d in error.value.diagnostics)
    return [(d.code, d.element) for d in error.value.diagnostics]


def test_a_duplicate_id_is_reported_once_per_id() -> None:
    twin = Element("m:e", "Another label", Kind.EVIDENCE)
    with pytest.raises(InvalidJustificationError) as error:
        model(elements=(CONCLUSION, STRATEGY, EVIDENCE, twin, twin))
    assert codes(error) == [("JP002", "m:e")]


@pytest.mark.parametrize(
    ("alias", "first_designated"),
    [
        pytest.param("a:s", "m:s", id="an alias of another element"),
        pytest.param("m:c", "m:c", id="the id of another element"),
    ],
)
def test_an_id_or_alias_designating_two_elements_is_reported(
    alias: str, first_designated: str
) -> None:
    evidence = Element("m:e", "The tests pass", Kind.EVIDENCE, (alias,))
    with pytest.raises(InvalidJustificationError) as error:
        model(elements=(CONCLUSION, STRATEGY, evidence))
    assert codes(error) == [("JP002", first_designated)]


def test_an_element_repeating_its_own_id_as_an_alias_is_one_element() -> None:
    evidence = Element("m:e", "The tests pass", Kind.EVIDENCE, ("m:e",))
    assert model(elements=(CONCLUSION, STRATEGY, evidence)).element("m:e") is evidence


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
    elements = (CONCLUSION, STRATEGY, EVIDENCE, EVIDENCE, STRATEGY)
    relations = (Relation("m:x", "m:c"), Relation("m:e", "m:y"))
    with pytest.raises(InvalidJustificationError) as error:
        model(elements=elements, relations=relations)
    assert codes(error) == [("JP002", "m:s"), ("JP002", "m:e"), ("JP003", None), ("JP003", None)]


def test_the_error_message_lists_the_diagnostics() -> None:
    problems = [
        Diagnostic("JP002", Severity.ERROR, "first", element="m:e"),
        Diagnostic("JP003", Severity.ERROR, "second"),
    ]
    assert str(InvalidJustificationError(problems)) == (
        "JP002 error [m:e]: first\nJP003 error: second"
    )
