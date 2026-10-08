import functools
import importlib
import inspect
import sys
import textwrap
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

import jpipe_runner
from jpipe_runner import Fail, Outcome, Pass, conclusion, evidence, strategy, sub_conclusion
from jpipe_runner.model import Kind
from jpipe_runner.steps import Step, StepRegistry, step_of


def test_the_package_exports_the_authoring_api() -> None:
    assert set(jpipe_runner.__all__) == {
        "evidence",
        "strategy",
        "sub_conclusion",
        "conclusion",
        "Outcome",
        "Pass",
        "Fail",
        "Skip",
        "__version__",
    }


def test_a_decorator_returns_the_function_itself() -> None:
    def the_tests_pass() -> Outcome:
        return Pass(tests_pass=True)

    decorated = evidence("m:e")(the_tests_pass)
    assert decorated is the_tests_pass
    assert decorated() == Pass(tests_pass=True)


@pytest.mark.parametrize(
    ("decorator", "kind", "consumes", "produces"),
    [
        pytest.param(evidence("m:x", produces=["a"]), Kind.EVIDENCE, (), ("a",), id="evidence"),
        pytest.param(
            strategy("m:x", consumes=["a"], produces=["b"]),
            Kind.STRATEGY,
            ("a",),
            ("b",),
            id="strategy",
        ),
        pytest.param(
            sub_conclusion("m:x", consumes=["a"], produces=["b"]),
            Kind.SUB_CONCLUSION,
            ("a",),
            ("b",),
            id="sub_conclusion",
        ),
        pytest.param(
            conclusion("m:x", consumes=["a"]), Kind.CONCLUSION, ("a",), (), id="conclusion"
        ),
    ],
)
def test_the_decorator_is_the_kind(
    decorator: Callable[[Callable[..., Outcome]], Callable[..., Outcome]],
    kind: Kind,
    consumes: tuple[str, ...],
    produces: tuple[str, ...],
) -> None:
    def function(a: int = 0) -> Outcome:
        return Pass()

    assert step_of(decorator(function)) == Step(kind, ("m:x",), function, consumes, produces)


def test_evidence_consumes_nothing_and_a_conclusion_produces_nothing() -> None:
    assert "consumes" not in inspect.signature(evidence).parameters
    assert "produces" not in inspect.signature(conclusion).parameters
    with pytest.raises(TypeError):
        evidence("m:e", consumes=["a"])  # type: ignore[call-arg]


def test_ids_are_positional_one_or_many() -> None:
    @evidence("rigor:r17:e_metric", "rigor:r18:e")
    def report_metrics() -> Outcome:
        return Pass()

    step = step_of(report_metrics)
    assert step is not None
    assert step.ids == ("rigor:r17:e_metric", "rigor:r18:e")


def test_variables_are_kept_in_the_order_given_from_any_iterable() -> None:
    @strategy("m:s", consumes=("b", "a"), produces=iter(["d", "c"]))
    def combine(a: int, b: int) -> Outcome:
        return Pass()

    step = step_of(combine)
    assert step is not None
    assert (step.consumes, step.produces) == (("b", "a"), ("d", "c"))


def test_a_step_is_named_by_its_module_and_qualified_name() -> None:
    @conclusion("m:c")
    def holds() -> Outcome:
        return Pass()

    step = step_of(holds)
    assert step is not None
    assert (
        step.name
        == f"{__name__}.test_a_step_is_named_by_its_module_and_qualified_name.<locals>.holds"
    )


def test_a_step_may_consume_what_it_produces() -> None:
    # A self-dependency is a fact about the dataflow, reported by validation (#119).
    @strategy("m:s", consumes=["a"], produces=["a"])
    def loop(a: int) -> Outcome:
        return Pass(a=a)

    assert step_of(loop) is not None


@pytest.mark.parametrize(
    "declare",
    [
        pytest.param(lambda: evidence(), id="no id"),
        pytest.param(lambda: evidence(""), id="empty id"),
        pytest.param(lambda: evidence("  "), id="blank id"),
        pytest.param(lambda: evidence(1), id="int id"),
        pytest.param(lambda: evidence("m:e", "m:e"), id="id twice"),
        pytest.param(lambda: evidence("m:e", produces="a"), id="produces a string"),
        pytest.param(lambda: strategy("m:s", consumes="a"), id="consumes a string"),
        pytest.param(lambda: evidence("m:e", produces=["a-b"]), id="not an identifier"),
        pytest.param(lambda: evidence("m:e", produces=["class"]), id="a keyword"),
        pytest.param(lambda: evidence("m:e", produces=[1]), id="not a string"),
        pytest.param(lambda: strategy("m:s", consumes=["a", "a"]), id="variable twice"),
    ],
)
def test_a_malformed_declaration_is_a_type_error(declare: Callable[[], object]) -> None:
    with pytest.raises(TypeError):
        declare()


def test_a_decorator_without_its_ids_is_a_type_error() -> None:
    def the_tests_pass() -> Outcome:
        return Pass()

    with pytest.raises(TypeError, match="ids"):
        evidence(the_tests_pass)  # type: ignore[arg-type]


def test_only_a_function_is_declared() -> None:
    declare = evidence("m:e")
    with pytest.raises(TypeError):
        declare(print)  # type: ignore[arg-type]


def test_a_function_is_one_step() -> None:
    @evidence("m:e")
    def the_tests_pass() -> Outcome:
        return Pass()

    declare = strategy("m:s")
    with pytest.raises(TypeError, match="already declared"):
        declare(the_tests_pass)


def _not_consumed(a: int) -> Outcome:
    return Pass()


def _positional_only(a: int, /) -> Outcome:
    return Pass()


def _no_parameters() -> Outcome:
    return Pass()


@pytest.mark.parametrize(
    ("function", "consumes"),
    [
        pytest.param(_not_consumed, [], id="a parameter that is not consumed"),
        pytest.param(_no_parameters, ["a"], id="a consumed variable that is not a parameter"),
        pytest.param(_positional_only, ["a"], id="a consumed variable passed only by position"),
    ],
)
def test_the_parameters_are_the_consumed_variables(
    function: Callable[..., Outcome], consumes: list[str]
) -> None:
    declare = strategy("m:s", consumes=consumes)
    with pytest.raises(TypeError, match="consume"):
        declare(function)


def test_a_parameter_with_a_default_or_keywords_need_not_match() -> None:
    @strategy("m:s", consumes=["a", "b"])
    def takes_any(a: int, timeout: float = 1.0, **others: Any) -> Outcome:
        return Pass()

    @conclusion("m:c", consumes=["a"])
    def keyword_only(*, a: int) -> Outcome:
        return Pass() if a else Fail("no a")

    assert step_of(takes_any) is not None
    assert step_of(keyword_only) is not None


def test_a_wrapper_of_a_step_is_the_step() -> None:
    @evidence("m:e")
    def inner() -> Outcome:
        return Pass()

    @functools.wraps(inner)
    def logged() -> Outcome:
        return inner()

    assert step_of(logged) == Step(Kind.EVIDENCE, ("m:e",), logged)


@pytest.mark.parametrize("candidate", [None, 1, "m:e", print, _no_parameters], ids=repr)
def test_anything_undeclared_is_not_a_step(candidate: object) -> None:
    assert step_of(candidate) is None


def _module(name: str, source: str) -> ModuleType:
    module = ModuleType(name)
    exec(textwrap.dedent(source), module.__dict__)
    return module


FIRST = """
    from jpipe_runner import Pass, evidence, strategy

    @evidence("m:e1", produces=["a"])
    def first():
        return Pass(a=1)

    def helper():
        return 1

    @strategy("m:s", consumes=["a"])
    def second(a):
        return Pass()
"""


def test_a_registry_lists_the_steps_of_its_modules_in_order() -> None:
    module = _module("first", FIRST)
    registry = StepRegistry.from_modules([module])
    assert [step.function for step in registry] == [module.first, module.second]
    assert len(registry) == 2
    assert repr(registry) == "StepRegistry(2 steps)"


def test_a_step_exposed_by_two_modules_is_listed_once() -> None:
    first = _module("first", FIRST)
    second = _module("second", "")
    second.reexported = first.first
    registry = StepRegistry.from_modules([second, first])
    assert [step.function for step in registry] == [first.first, first.second]


def test_a_registry_holds_declarations_and_two_are_independent() -> None:
    module = _module("first", FIRST)
    one, other = StepRegistry.from_modules([module]), StepRegistry.from_modules([module])
    assert one is not other
    assert one.steps == other.steps


def test_the_v3_api_says_what_replaced_it() -> None:
    with pytest.raises(ImportError, match="@evidence") as raised:
        importlib.import_module("jpipe_runner.framework.decorators.jpipe_decorator")
    assert raised.value.name == "jpipe_runner.framework"
    assert "jpipe_runner.framework" not in sys.modules
