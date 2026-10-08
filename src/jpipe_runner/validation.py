"""Validation: checking a step library against its model before anything runs (ADR-0010).

A ``Rule`` is one check, reified as a class. Its ``code``, ``severity`` and ``summary`` are
class attributes and its docstring says what it checks, why, and how to fix what it
reports, so that a human can audit every rule in one place: ``docs/rules.md`` is generated
from them. A ``RuleSet`` runs every rule over a ``ValidationContext`` and collects every
diagnostic in a ``ValidationReport``, so one problem never hides another.

Severity is real. An ``ERROR`` blocks execution; a ``WARNING`` is reported and the run
continues, unless the run is strict, which counts warnings as errors. No rule can be
disabled.

What the model alone shows to be unrunnable (JP001 to JP004) is refused when it is loaded,
not by a rule: a ``Justification`` that exists is valid.
"""

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import ClassVar

from jpipe_runner.binding import Binding, BindingTable
from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.model import Justification
from jpipe_runner.steps import StepRegistry

_CODE = re.compile(r"JP\d{3}")


@dataclass(frozen=True)
class ValidationContext:
    """What a rule checks: a model, a step library, and the binding of one to the other."""

    justification: Justification
    registry: StepRegistry
    bindings: BindingTable

    @classmethod
    def of(cls, justification: Justification, registry: StepRegistry) -> "ValidationContext":
        """The context of ``registry``'s steps bound to ``justification``'s elements."""
        return cls(justification, registry, BindingTable(justification, registry))

    @cached_property
    def producers(self) -> Mapping[str, tuple[Binding, ...]]:
        """The bound steps that produce each variable, in model order.

        Only bound steps count: a step that binds no element never runs, so nothing it
        declares is ever produced.
        """
        return _index(self.bindings, lambda binding: binding.step.produces)

    @cached_property
    def consumers(self) -> Mapping[str, tuple[Binding, ...]]:
        """The bound steps that consume each variable, in model order."""
        return _index(self.bindings, lambda binding: binding.step.consumes)


class Rule(ABC):
    """One validation check. A subclass sets ``code``, ``severity`` and ``summary``, and
    its docstring says what it checks, why it matters, and how to fix what it reports."""

    code: ClassVar[str]
    """``JPnnn``: what reports, tests and users rely on. It never changes meaning."""
    severity: ClassVar[Severity]
    summary: ClassVar[str]
    """One sentence stating the problem the rule reports."""

    @abstractmethod
    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        """Every instance of the problem in ``ctx``, each as a diagnostic with this code."""

    def diagnostic(
        self, message: str, *, element: str | None = None, fix: str | None = None
    ) -> Diagnostic:
        """A diagnostic carrying this rule's code and severity."""
        return Diagnostic(self.code, self.severity, message, element=element, fix=fix)

    @property
    def name(self) -> str:
        return type(self).__name__

    def __repr__(self) -> str:
        return f"{self.name}({self.code}, {self.severity})"


@dataclass(frozen=True)
class ValidationReport:
    """Every diagnostic the rules reported, ordered by code, then as each rule found them."""

    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return self._of(Severity.ERROR)

    @property
    def warnings(self) -> tuple[Diagnostic, ...]:
        return self._of(Severity.WARNING)

    @property
    def passed(self) -> bool:
        """Whether the steps can run: no error was reported."""
        return not self.errors

    def _of(self, severity: Severity) -> tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity is severity)


class RuleSet:
    """Rules, run together, in the order of their codes.

    Every rule must be auditable: a ``JPnnn`` code used by no other rule, a severity, a
    summary and a docstring. A rule that lacks one is a ``TypeError`` here.
    """

    def __init__(self, rules: Iterable[Rule]) -> None:
        given = tuple(rules)
        for rule in given:
            _check_metadata(rule)
        self._rules = tuple(sorted(given, key=lambda rule: rule.code))
        codes = [rule.code for rule in self._rules]
        if repeated := sorted({code for code in codes if codes.count(code) > 1}):
            raise TypeError(f"several rules have the code {', '.join(repeated)}")

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    def run(self, ctx: ValidationContext, *, strict: bool = False) -> ValidationReport:
        """Run every rule over ``ctx``. ``strict`` reports every warning as an error.

        A rule reports with its own code and severity, or the documentation of the rules,
        and the blocking of errors, would not hold: anything else is a bug, and raises.
        """
        found: list[Diagnostic] = []
        for rule in self._rules:
            for diagnostic in rule.check(ctx):
                if (diagnostic.code, diagnostic.severity) != (rule.code, rule.severity):
                    raise RuntimeError(
                        f"{rule.name} reported a {diagnostic.code} {diagnostic.severity}, "
                        f"not a {rule.code} {rule.severity}"
                    )
                found.append(diagnostic)
        if strict:
            found = [_promoted(diagnostic) for diagnostic in found]
        return ValidationReport(tuple(found))

    def __iter__(self) -> Iterator[Rule]:
        return iter(self._rules)

    def __len__(self) -> int:
        return len(self._rules)

    def __repr__(self) -> str:
        return f"RuleSet({', '.join(rule.code for rule in self._rules)})"


def _index(
    bindings: BindingTable, variables: Callable[[Binding], tuple[str, ...]]
) -> Mapping[str, tuple[Binding, ...]]:
    index: dict[str, list[Binding]] = {}
    for binding in bindings:
        for variable in variables(binding):
            index.setdefault(variable, []).append(binding)
    return {variable: tuple(found) for variable, found in index.items()}


def _check_metadata(rule: Rule) -> None:
    name = rule.name
    code = getattr(rule, "code", None)
    if not isinstance(code, str) or not _CODE.fullmatch(code):
        raise TypeError(f"{name}: code must be 'JPnnn', not {code!r}")
    if not isinstance(getattr(rule, "severity", None), Severity):
        raise TypeError(f"{name}: severity must be a Severity")
    if not isinstance(getattr(rule, "summary", None), str) or not rule.summary.strip():
        raise TypeError(f"{name}: summary must say, in one sentence, what the rule reports")
    if not (type(rule).__doc__ or "").strip():
        raise TypeError(f"{name}: a rule's docstring says what it checks, why, and how to fix it")


def _promoted(diagnostic: Diagnostic) -> Diagnostic:
    if diagnostic.severity is not Severity.WARNING:
        return diagnostic
    return Diagnostic(
        diagnostic.code, Severity.ERROR, diagnostic.message, diagnostic.element, diagnostic.fix
    )
