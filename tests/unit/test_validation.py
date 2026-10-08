"""The validation framework: rules, rule sets, contexts and reports (ADR-0010).

The rules themselves are tested one module each, under tests/unit/validation/rules/.
"""

from collections.abc import Iterator
from typing import ClassVar

import pytest

from jpipe_runner import Outcome, Pass, evidence, strategy
from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.model import Element, Justification, Kind, Relation
from jpipe_runner.steps import StepRegistry, step_of
from jpipe_runner.validation import Rule, RuleSet, ValidationContext, ValidationReport

E1 = Element("m:e1", "The tests pass", Kind.EVIDENCE)
E2 = Element("m:e2", "The linter passes", Kind.EVIDENCE)
S = Element("m:s", "Both checks pass", Kind.STRATEGY)
MODEL = Justification("m", (E1, E2, S), (Relation(E1.id, S.id), Relation(E2.id, S.id)))


@evidence("m:e2", produces=["lint_ok"])
def lint() -> Outcome:
    return Pass(lint_ok=True)


@evidence("m:e1", produces=["tests_ok"])
def suite() -> Outcome:
    return Pass(tests_ok=True)


@strategy("m:s", consumes=["tests_ok", "lint_ok"])
def both(tests_ok: bool, lint_ok: bool) -> Outcome:
    return Pass()


@evidence("m:nowhere", produces=["tests_ok"])
def unbound() -> Outcome:
    return Pass(tests_ok=True)


def context(*functions: object) -> ValidationContext:
    steps = [step_of(function) for function in functions]
    return ValidationContext.of(MODEL, StepRegistry(step for step in steps if step))


class Fires(Rule):
    """Reports every bound element, as a warning."""

    code = "JP901"
    severity = Severity.WARNING
    summary = "An element is bound."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for binding in ctx.bindings:
            yield self.diagnostic("bound", element=binding.element.id, fix="Unbind it.")


class Blocks(Rule):
    """Reports the model, as an error."""

    code = "JP900"
    severity = Severity.ERROR
    summary = "The model exists."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        yield self.diagnostic(f"{ctx.justification.name} exists")


class Informs(Rule):
    """Reports the model, for information."""

    code = "JP902"
    severity = Severity.INFO
    summary = "The model has a name."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        yield self.diagnostic(ctx.justification.name)


def test_the_context_binds_the_registry_to_the_model() -> None:
    ctx = context(suite, lint, both)
    assert ctx.justification is MODEL
    assert [binding.element for binding in ctx.bindings] == [E1, E2, S]
    assert ctx.bindings.diagnostics == ()


def test_producers_and_consumers_are_bound_steps_in_model_order() -> None:
    ctx = context(lint, suite, both, unbound)
    assert {name: [b.element.id for b in found] for name, found in ctx.producers.items()} == {
        "tests_ok": ["m:e1"],
        "lint_ok": ["m:e2"],
    }
    assert {name: [b.element.id for b in found] for name, found in ctx.consumers.items()} == {
        "tests_ok": ["m:s"],
        "lint_ok": ["m:s"],
    }


def test_a_rule_reports_with_its_own_code_and_severity() -> None:
    (diagnostic, *_) = Fires().check(context(suite))
    assert diagnostic == Diagnostic("JP901", Severity.WARNING, "bound", "m:e1", "Unbind it.")
    assert Fires().name == "Fires"
    assert repr(Fires()) == "Fires(JP901, warning)"


def test_a_rule_set_runs_its_rules_in_code_order_and_keeps_every_diagnostic() -> None:
    rules = RuleSet([Fires(), Informs(), Blocks()])
    assert [rule.code for rule in rules] == ["JP900", "JP901", "JP902"]
    assert [rule.code for rule in rules.rules] == ["JP900", "JP901", "JP902"]
    assert len(rules) == 3
    assert repr(rules) == "RuleSet(JP900, JP901, JP902)"

    report = rules.run(context(suite, lint, both))
    assert [(d.code, d.element) for d in report.diagnostics] == [
        ("JP900", None),
        ("JP901", "m:e1"),
        ("JP901", "m:e2"),
        ("JP901", "m:s"),
        ("JP902", None),
    ]
    assert [d.code for d in report.errors] == ["JP900"]
    assert [d.code for d in report.warnings] == ["JP901"] * 3
    assert not report.passed


def test_warnings_do_not_block_the_run() -> None:
    report = RuleSet([Fires(), Informs()]).run(context(suite))
    assert report.warnings
    assert report.errors == ()
    assert report.passed


def test_a_strict_run_reports_warnings_as_errors_and_leaves_information_alone() -> None:
    report = RuleSet([Fires(), Informs()]).run(context(suite), strict=True)
    assert [(d.code, d.severity) for d in report.diagnostics] == [
        ("JP901", Severity.ERROR),
        ("JP902", Severity.INFO),
    ]
    assert not report.passed


def test_an_empty_report_passes() -> None:
    assert ValidationReport().passed
    assert RuleSet([]).run(context()).diagnostics == ()


def test_two_rules_cannot_share_a_code() -> None:
    class Again(Fires):
        """The same code as Fires."""

    rules = [Fires(), Again()]
    with pytest.raises(TypeError, match="JP901"):
        RuleSet(rules)


@pytest.mark.parametrize(
    ("attributes", "problem"),
    [
        pytest.param({"code": "E901"}, "code", id="not a JP code"),
        pytest.param({"code": None}, "code", id="no code"),
        pytest.param({"severity": "warning"}, "severity", id="severity as a string"),
        pytest.param({"summary": " "}, "summary", id="blank summary"),
        pytest.param({"__doc__": None}, "docstring", id="no docstring"),
    ],
)
def test_a_rule_that_cannot_be_audited_is_refused(
    attributes: dict[str, object], problem: str
) -> None:
    unaudited = type("Unaudited", (Fires,), {"__doc__": "Documented.", **attributes})()
    with pytest.raises(TypeError, match=problem):
        RuleSet([unaudited])


def test_a_rule_without_a_code_is_refused_before_the_rules_are_ordered() -> None:
    class Uncoded(Rule):
        """Declares no code at all."""

        severity = Severity.ERROR
        summary = "Has no code."

        def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
            yield from ()

    rules = [Fires(), Uncoded()]
    with pytest.raises(TypeError, match="Uncoded: code"):
        RuleSet(rules)


def test_a_rule_reporting_another_code_is_a_bug() -> None:
    class Liar(Rule):
        """Reports under a code that is not its own."""

        code: ClassVar[str] = "JP903"
        severity = Severity.ERROR
        summary = "Lies."

        def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
            yield Diagnostic("JP904", Severity.ERROR, "not mine")

    rules, ctx = RuleSet([Liar()]), context()
    with pytest.raises(RuntimeError, match="JP904"):
        rules.run(ctx)


def test_a_rule_reporting_another_severity_is_a_bug() -> None:
    class Softened(Rule):
        """Reports its own code, but as a warning although it is an error."""

        code: ClassVar[str] = "JP905"
        severity = Severity.ERROR
        summary = "Softens."

        def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
            yield Diagnostic("JP905", Severity.WARNING, "only a warning")

    rules, ctx = RuleSet([Softened()]), context()
    with pytest.raises(RuntimeError, match="warning"):
        rules.run(ctx)
