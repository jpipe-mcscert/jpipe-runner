import dataclasses
from typing import Any

import pytest

import jpipe_runner
from jpipe_runner.diagnostics import Severity
from jpipe_runner.outcomes import (
    NOT_AN_OUTCOME,
    Fail,
    NotAnOutcomeError,
    Outcome,
    Pass,
    Skip,
    as_outcome,
)


def test_outcomes_are_exported_from_the_package() -> None:
    assert (jpipe_runner.Outcome, jpipe_runner.Pass, jpipe_runner.Fail, jpipe_runner.Skip) == (
        Outcome,
        Pass,
        Fail,
        Skip,
    )


@pytest.mark.parametrize("outcome", [Pass(), Fail("no"), Skip()], ids=repr)
def test_every_outcome_is_an_outcome(outcome: Outcome) -> None:
    assert isinstance(outcome, Outcome)


def test_outcome_itself_is_not_instantiated() -> None:
    with pytest.raises(TypeError, match="Pass"):
        Outcome()


@pytest.mark.parametrize(
    ("outcome", "values"),
    [
        pytest.param(Pass(), {}, id="nothing"),
        pytest.param(Pass({"a": 1}), {"a": 1}, id="mapping"),
        pytest.param(Pass(a=1), {"a": 1}, id="keywords"),
        pytest.param(Pass({"a": 1}, b=2), {"a": 1, "b": 2}, id="both"),
        # The mapping is positional-only, so its parameter name is free for a variable.
        pytest.param(Pass(values=1), {"values": 1}, id="values-as-a-variable"),
    ],
)
def test_pass_takes_a_mapping_keywords_or_both(outcome: Pass, values: dict[str, Any]) -> None:
    assert dict(outcome.values) == values


def test_a_name_given_twice_to_pass_is_refused() -> None:
    with pytest.raises(TypeError, match="'a'"):
        Pass({"a": 1}, a=2)


@pytest.mark.parametrize("values", [False, 0, "", ["a"], "a"], ids=repr)
def test_pass_takes_a_mapping_and_nothing_else(values: object) -> None:
    with pytest.raises(TypeError, match="mapping"):
        Pass(values)  # type: ignore[arg-type]


def test_pass_copies_every_entry_of_a_mapping_however_it_tests_as_a_boolean() -> None:
    class AlwaysFalse(dict[str, int]):
        def __bool__(self) -> bool:
            return False

    assert dict(Pass(AlwaysFalse(a=1)).values) == {"a": 1}


def test_produced_variables_are_named_by_strings() -> None:
    mapping: dict[Any, int] = {1: 1}
    with pytest.raises(TypeError, match="str"):
        Pass(mapping)


def test_pass_copies_the_mapping_it_is_given() -> None:
    produced = {"a": 1}
    outcome = Pass(produced)
    produced["a"] = 2
    assert outcome.values["a"] == 1


@pytest.mark.parametrize("outcome", [Pass(a=1), Fail("no"), Skip("later")], ids=repr)
def test_outcomes_are_frozen(outcome: Outcome) -> None:
    field = dataclasses.fields(outcome)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(outcome, field, None)


def test_produced_values_cannot_be_changed() -> None:
    outcome = Pass(a=1)
    with pytest.raises(TypeError):
        outcome.values["a"] = 2  # type: ignore[index]


def test_outcomes_compare_by_kind_and_content() -> None:
    assert Pass(a=1) == Pass({"a": 1})
    assert Pass(a=1) != Pass(a=2)
    assert Fail("x") == Fail(reason="x")
    assert Fail("x") != Skip("x")


def test_skip_needs_no_reason_and_fail_does() -> None:
    assert Skip().reason == ""
    assert Fail("mock/tests.ok not found").reason == "mock/tests.ok not found"
    with pytest.raises(TypeError):
        Fail()  # type: ignore[call-arg]


@pytest.mark.parametrize("make", [Fail, Skip])
def test_a_reason_is_a_string(make: type[Fail] | type[Skip]) -> None:
    with pytest.raises(TypeError, match="str"):
        make(False)  # type: ignore[arg-type]


def test_outcomes_read_as_they_are_written() -> None:
    assert repr(Pass()) == "Pass()"
    assert repr(Pass(a=1)) == "Pass({'a': 1})"
    assert repr(Fail("no")) == "Fail(reason='no')"
    assert repr(Skip()) == "Skip(reason='')"


@pytest.mark.parametrize("outcome", [Pass(a=1), Fail("no"), Skip()], ids=repr)
def test_an_outcome_is_returned_as_is(outcome: Outcome) -> None:
    assert as_outcome(outcome, "m:e") is outcome


@pytest.mark.parametrize(
    ("returned", "replacement"),
    [
        pytest.param(True, "Pass()", id="True"),
        pytest.param(False, "Fail(reason)", id="False"),
        pytest.param(None, "Pass(), Fail(reason) or Skip(reason)", id="None"),
        pytest.param({"a": 1}, "Pass(values)", id="dict"),
        pytest.param(1, "Pass(), Fail(reason) or Skip(reason)", id="int"),
        pytest.param("ok", "Pass(), Fail(reason) or Skip(reason)", id="str"),
    ],
)
def test_anything_else_is_jp017_naming_the_replacement(returned: object, replacement: str) -> None:
    with pytest.raises(NotAnOutcomeError) as raised:
        as_outcome(returned, "m:e")
    diagnostic = raised.value.diagnostic
    assert (diagnostic.code, diagnostic.severity, diagnostic.element) == (
        NOT_AN_OUTCOME,
        Severity.ERROR,
        "m:e",
    )
    assert diagnostic.fix is not None
    assert replacement in diagnostic.fix
