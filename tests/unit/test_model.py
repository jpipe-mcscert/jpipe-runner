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
    with pytest.raises(KeyError, match="m:x"):
        getattr(model(), query)("m:x")


def test_elements_are_looked_up_by_their_own_id() -> None:
    justification = model()
    assert justification.element("m:s") is STRATEGY
    assert "m:s" in justification
    assert "a:s" not in justification  # aliases are resolved by binding (#115), not here
    assert 1 not in justification
    assert ["m:s"] not in justification


def test_an_acyclic_model_has_no_cycle() -> None:
    assert model().cycle() is None


def test_a_cycle_is_reported_and_left_to_validation() -> None:
    cyclic = model(relations=(*RELATIONS, Relation("m:c", "m:e")))
    cycle = cyclic.cycle()
    assert cycle is not None
    assert sorted(cycle) == ["m:c", "m:e", "m:s"]
    assert {(a, b) for a, b in zip(cycle, (*cycle[1:], cycle[0]), strict=True)} <= {
        (r.source, r.target) for r in cyclic.relations
    }
    with pytest.raises(ValueError, match="cycle"):
        cyclic.topological_order()


def test_an_element_supporting_itself_is_a_cycle() -> None:
    assert model(relations=(*RELATIONS, Relation("m:e", "m:e"))).cycle() == ("m:e",)


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
