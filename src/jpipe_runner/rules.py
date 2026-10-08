"""The validation rules: every check run on a step library against its model (#119).

Each rule is a class, written to be audited by a human: ``code``, ``severity`` and
``summary`` say what it reports, and its docstring says what it checks, why, and how to
fix what it reports. ``docs/rules.md`` is generated from this module (ADR-0010, #128).

``RULES`` is the rule set every run uses.
"""

from collections.abc import Iterator

from jpipe_runner import binding
from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.validation import Rule, RuleSet, ValidationContext


class _FromBindingTable(Rule):
    """Reports what the binding table found under this rule's code (ADR-0007)."""

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        return (d for d in ctx.bindings.diagnostics if d.code == self.code)


class AmbiguousBinding(_FromBindingTable):
    """A step's id is a tail of the ids of several elements, so it designates none of them.

    An id designates an element when it is the element's id or one of its aliases, that id
    qualified by the justification's name, or a strictly shorter tail of either, cut at
    `:` ([ADR-0007](adr/0007-binding-resolution.md)). An exact match always wins. A tail that
    ends the ids of two elements is not resolved to either: the runner never guesses which
    element a step implements. A tail unique today can become ambiguous when the model
    grows, or is composed with another.

    **Fix:** use a longer id, which designates one element, such as the id the compiler
    exports.
    """

    code = binding.AMBIGUOUS_BINDING
    severity = Severity.ERROR
    summary = "An id designates several elements."


class ConflictingBinding(_FromBindingTable):
    """An element is bound by several steps, or a step's ids designate several elements.

    Binding is one to one: an element is implemented by at most one function, and a
    function implements exactly one element. Two functions for one claim would give it two
    verdicts; one function for two claims would produce its variables twice. The element
    or the step in conflict is left unbound.

    After `refine`, the hook and the refinement's conclusion are one element, which
    answers to both ids: binding both is a conflict, not a cross-check.

    **Fix:** keep one function per element. When two elements are checked the same way,
    share the code in a helper, not the step.
    """

    code = binding.CONFLICTING_BINDING
    severity = Severity.ERROR
    summary = "An element is bound by several steps, or a step to several elements."


class UnknownBindingTarget(_FromBindingTable):
    """A step's id designates no element of the model, so the step would never run.

    v3 ignored such an id silently: a typo meant the check was never run, and nothing said
    so. The step's other ids may still bind it.

    **Fix:** use the id of an element of the model, as the compiler exports it, or a unique
    tail of it.
    """

    code = binding.UNKNOWN_BINDING_TARGET
    severity = Severity.ERROR
    summary = "An id designates no element of the model."


RULES = RuleSet([AmbiguousBinding(), ConflictingBinding(), UnknownBindingTarget()])
"""Every rule, run on every validation."""
