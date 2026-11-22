"""The validation rules: every check run on a step library against its model (#119).

Each rule is a class, written to be audited by a human: ``code``, ``severity`` and
``summary`` say what it reports, and its docstring says what it checks, why, and how to
fix what it reports. ``docs/rules.md`` is generated from this module (ADR-0010, #128).

``RULES`` is the rule set every run uses. ``RETIRED`` lists the codes no rule reports any
more: a code never changes meaning, so a retired one is never reused.
"""

from collections.abc import Iterator, Mapping

from jpipe_runner import binding
from jpipe_runner.binding import Binding
from jpipe_runner.dataflow import Consumption
from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.model import Kind
from jpipe_runner.validation import Rule, RuleSet, ValidationContext


class _FromBindingTable(Rule):
    """Reports what binding found under this rule's code (ADR-0007): the ids of the steps,
    and the ids that name a producer with `Produced(variable, by=id)` (ADR-0031)."""

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        found = (*ctx.bindings.diagnostics, *ctx.dataflow.diagnostics)
        return (d for d in found if d.code == self.code)


class AmbiguousBinding(_FromBindingTable):
    """A step's id is a tail of the ids of several elements, so it designates none of them.

    An id designates an element when it is the element's id or one of its aliases, that id
    qualified by the justification's name, or a strictly shorter tail of either, cut at
    `:` ([ADR-0007](adr/0007-binding-resolution.md)). An exact match always wins. A tail that
    ends the ids of two elements is not resolved to either: the runner never guesses which
    element a step implements. A tail unique today can become ambiguous when the model
    grows, or is composed with another. The id a step gives as `by`, in
    `Produced(variable, by=id)`, designates an element in the same way.

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
    so. The step's other ids may still bind it. The id a step gives as `by`, in
    `Produced(variable, by=id)`, must designate an element too: otherwise, nothing says
    which value the step receives.

    **Fix:** use the id of an element of the model, as the compiler exports it, or a unique
    tail of it.
    """

    code = binding.UNKNOWN_BINDING_TARGET
    severity = Severity.ERROR
    summary = "An id designates no element of the model."


class UnboundElement(Rule):
    """An evidence or a strategy of the model has no step.

    Evidence and strategies are where an argument is checked: an evidence's step observes
    the world, a strategy's judges what its supporters found. Without a step, the claim
    they stand for would be accepted unchecked. Conclusions and sub-conclusions are
    optional: an unbound one takes its status from what supports it. An element left
    unbound by a conflict, claimed by several steps or designated by a step whose ids
    designate several elements, is reported by `JP007` instead.

    **Fix:** write its step, `@evidence("id")` or `@strategy("id")`.
    """

    code = "JP005"
    severity = Severity.ERROR
    summary = "An evidence or a strategy has no step."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for element in ctx.justification:
            if element.kind not in (Kind.EVIDENCE, Kind.STRATEGY):
                continue
            if (
                ctx.bindings.step_for(element.id) is None
                and element.id not in ctx.bindings.contested
            ):
                yield self.diagnostic(
                    f"the {element.kind} {element.label!r} has no step, so nothing checks it",
                    element=element.id,
                    fix=f'Write its step: {element.kind.decorator}("{element.id}").',
                )


class RefinedElement(Rule):
    """A step declared as evidence or conclusion is bound to what the model calls a
    sub-conclusion.

    Composition changes kinds, in one direction only
    ([ADR-0013](adr/0013-kind-divergence-under-composition.md)):

    - `refine` merges the hook evidence and the refinement's conclusion into one
      sub-conclusion;
    - `assemble` turns the conclusion of each source into a sub-conclusion;
    - unification merges an evidence into a sub-conclusion with the same label.

    A step written against the model before it was composed keeps binding, to an element
    that is now argued in full below it. That is the intended workflow: the step runs
    after the sub-argument, as an independent cross-check of the same claim. It is
    reported so that the change is seen. It is not an error because the same library
    often still serves the model it was written for, where the element has its old kind.

    **Fix:** none, when the step is meant as a cross-check. When the library serves only
    the composed model, declare the step with `@sub_conclusion`, which may also consume
    what the sub-argument produces.
    """

    code = "JP008"
    severity = Severity.WARNING
    summary = "A step declared as evidence or conclusion is bound to a sub-conclusion."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for bound in ctx.bindings:
            if _composed(bound):
                yield self.diagnostic(
                    f"{bound.step.name} is declared as {bound.step.kind}, and is bound to "
                    f"a sub-conclusion: it runs as a cross-check of the argument below it",
                    element=bound.element.id,
                    fix="Nothing to do for a cross-check. If the library serves only the "
                    "composed model, declare the step with @sub_conclusion.",
                )


class MissingProducer(Rule):
    """A step consumes a variable that no step produces.

    Every value a step receives is produced by another step: there is no other source
    ([ADR-0008](adr/0008-drop-external-variable-injection.md)). A step that binds no
    element never runs, so what it declares does not count.

    **Fix:** produce the variable in a step that supports the consumer, or remove it from
    `consumes` and from the function's parameters.
    """

    code = "JP009"
    severity = Severity.ERROR
    summary = "A step consumes a variable that no step produces."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for consumed in _distinct(ctx):
            if not consumed.producers:
                variable = consumed.input.variable
                yield self.diagnostic(
                    f"{consumed.consumer.step.name} consumes {variable!r}, which no step produces",
                    element=consumed.consumer.element.id,
                    fix=f"Produce {variable!r} in a step that supports this one.",
                )


class UnconsumedOutput(Rule):
    """A step produces a variable that no step consumes.

    A value nothing reads is either computed for nothing, or meant for a step that forgot
    to consume it. An evidence that produces nothing anyone consumes is reported by
    `JP012` instead.

    **Fix:** consume the variable where it is needed, or stop producing it.
    """

    code = "JP011"
    severity = Severity.WARNING
    summary = "A step produces a variable that no step consumes."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for bound in ctx.bindings:
            if _evidence_without_use(bound, ctx):
                continue
            for variable in bound.step.produces:
                if not ctx.dataflow.users(bound.element.id, variable):
                    yield self.diagnostic(
                        f"{bound.step.name} produces {variable!r}, which no step consumes",
                        element=bound.element.id,
                        fix=f"Consume {variable!r} where it is needed, or stop producing it.",
                    )


class EvidenceProducesNothing(Rule):
    """An evidence step produces no value that another step consumes.

    Evidence observes the world and reports what it observed, as values, for the
    strategies above it to judge. An evidence that only passes or fails hands its
    strategy a verdict without the facts behind it, and a strategy cannot reason about
    what it is not given. Placeholder steps (`return Pass()`) are the usual cause.

    **Fix:** produce what the evidence observed (a count, a measure, a version), and
    consume it in the strategy that judges it.
    """

    code = "JP012"
    severity = Severity.ERROR
    summary = "An evidence produces no value that another step consumes."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for bound in ctx.bindings:
            if not _evidence_without_use(bound, ctx):
                continue
            produced = ", ".join(map(repr, bound.step.produces))
            what = (
                f"produces {produced}, which no step consumes" if produced else "produces nothing"
            )
            yield self.diagnostic(
                f"the evidence {bound.step.name} {what}",
                element=bound.element.id,
                fix="Produce what the evidence observed, and consume it in its strategy.",
            )


class StrategyIgnoresUpstreamOutput(Rule):
    """A strategy does not consume a variable that one of its supporters produces for
    another step.

    A strategy is the reasoning that turns what its supporters found into a claim. A value
    produced right below it and read only further up skips that reasoning: the strategy
    judges without looking at it. A value nobody consumes is reported by `JP011` or
    `JP012` instead. A value counts as read further up when a step above draws on that
    supporter's value, not merely on a variable of the same name.

    **Fix:** consume the variable in the strategy, or produce it where it is used.
    """

    code = "JP013"
    severity = Severity.WARNING
    summary = "A strategy ignores a value its supporters produce for another step."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for bound in ctx.bindings:
            if bound.element.kind is not Kind.STRATEGY:
                continue
            for supporter, variable in _produced_below(bound, ctx):
                users = ctx.dataflow.users(supporter, variable)
                if users and all(u.consumer.element.id != bound.element.id for u in users):
                    yield self.diagnostic(
                        f"{bound.step.name} ignores {variable!r}, which its supporter "
                        f"{supporter!r} produces",
                        element=bound.element.id,
                        fix=f"Consume {variable!r} in this strategy.",
                    )


class ConsumedBeforeProduced(Rule):
    """A step consumes a variable that no step supporting it produces.

    Steps run supporters first, and a step whose supporter fails or skips is skipped in
    turn. A value is therefore certain to exist when a step runs only if its producer
    supports that step, directly or not. Coming first in some order is not enough: a
    producer on another branch may fail and leave the consumer without its value. A step
    that consumes what it produces is the extreme case. So a consumed variable is looked
    for among the consumer's supporters only
    ([ADR-0031](adr/0031-variables-resolve-among-supporters.md)), and at or below the
    element named by `by`, when the step names one with `Produced(variable, by=id)`.

    **Fix:** produce the variable in a step that supports its consumer, or move the
    consumer above the producer in the argument. With `by`, name an element at or above
    the producer, among the consumer's supporters.
    """

    code = "JP014"
    severity = Severity.ERROR
    summary = "A step consumes a variable that no step supporting it produces."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for consumed in _distinct(ctx):
            if consumed.designated and consumed.producers and not consumed.candidates:
                yield self.diagnostic(
                    _unsupported(consumed),
                    element=consumed.consumer.element.id,
                    fix=f"Produce {consumed.input.variable!r} in a step that supports this one.",
                )


class IncompatibleKind(Rule):
    """A step's decorator declares a kind that its element cannot have become by
    composition.

    Composition only ever turns an evidence or a conclusion into a sub-conclusion
    (`JP008`). Any other difference between a step's kind and its element's, such as a
    `@strategy` bound to an evidence, is an authoring mistake: the step's signature is
    built for another kind of element.

    **Fix:** use the decorator of the element's kind, or bind the step to the element it
    was written for.
    """

    code = "JP016"
    severity = Severity.ERROR
    summary = "A step's kind differs from its element's, in a way composition cannot explain."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for bound in ctx.bindings:
            if bound.step.kind is not bound.element.kind and not _composed(bound):
                yield self.diagnostic(
                    f"{bound.step.name} is declared as {bound.step.kind}, but is bound to "
                    f"the {bound.element.kind} {bound.element.id!r}",
                    element=bound.element.id,
                    fix=f"Declare it with {bound.element.kind.decorator}.",
                )


class EvidenceObservesNothing(Rule):
    """An evidence step declares no artifact that it observes.

    Evidence is where an argument touches the world: a test report, a changelog, a
    configuration file. An evidence that observes nothing checks nothing in the world,
    whatever it returns. Placeholder steps (`return Pass()`) and skeletons left unfilled
    are the usual cause. In an assurance case, fake evidence is worse than missing
    evidence: it looks like a check. Declaring the artifacts also lets the runner check
    that they exist, record them, and archive them with the report
    ([ADR-0018](adr/0018-evidence-declares-observed-artifacts.md)).

    **Fix:** declare what the evidence observes, and take it as a parameter:
    `@evidence("id", observes={"changelog": "CHANGELOG.md"})`.
    """

    code = "JP018"
    severity = Severity.ERROR
    summary = "An evidence observes no artifact."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for bound in ctx.bindings:
            if bound.step.kind is Kind.EVIDENCE and not bound.step.observes:
                yield self.diagnostic(
                    f"the evidence {bound.step.name} observes no artifact, so it checks "
                    f"nothing in the world",
                    element=bound.element.id,
                    fix='Declare what it observes: observes={"name": "path/to/artifact"}.',
                )


class AmbiguousConsumption(Rule):
    """Several steps that support a step produce a variable it consumes.

    A step receives a variable from the one step among its supporters that produces it
    ([ADR-0031](adr/0031-variables-resolve-among-supporters.md)). Two steps may produce
    the same name, as libraries written apart for separate models do: each consumer then
    receives the value from its own sub-argument. A step that both support, such as the
    strategy `assemble` adds above them, sees both, and the runner never guesses which
    one it means, nor picks the nearer.

    **Fix:** name the part of the argument the value comes from, with
    `consumes={"parameter": Produced("variable", by="id")}`: `by` designates the producer,
    or an element it supports, such as the conclusion of its sub-argument. To take both
    values, map two parameters to the same variable, each with its own `by`.
    """

    code = "JP025"
    severity = Severity.ERROR
    summary = "Several steps that support a step produce a variable it consumes."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        for consumed in _distinct(ctx):
            if len(consumed.candidates) > 1:
                variable = consumed.input.variable
                ids = ", ".join(repr(p.element.id) for p in consumed.candidates)
                yield self.diagnostic(
                    f"{consumed.consumer.step.name} consumes {variable!r}, which "
                    f"{len(consumed.candidates)} of its supporters produce: {ids}",
                    element=consumed.consumer.element.id,
                    fix=_naming(consumed, ctx),
                )


def _naming(consumed: Consumption, ctx: ValidationContext) -> str:
    """The fix of a JP025: the entry of ``consumes`` to write for each parameter that
    receives the ambiguous variable, leaving the step's other entries as they are."""
    variable, by = consumed.input.variable, consumed.input.by
    example = consumed.candidates[0].element.id
    parameters = [
        c.input.parameter
        for c in ctx.dataflow.of(consumed.consumer.element.id)
        if (c.input.variable, c.input.by) == (variable, by)
    ]
    entries = ", ".join(f'"{p}": Produced("{variable}", by="{example}")' for p in parameters)
    which = "the one it means" if len(parameters) == 1 else "the one each parameter means"
    return f"Name {which}, keeping the other entries of consumes: {entries}."


def _composed(bound: Binding) -> bool:
    """Whether composition explains the kinds: evidence or conclusion turned sub-conclusion."""
    return bound.element.kind is Kind.SUB_CONCLUSION and bound.step.kind in (
        Kind.EVIDENCE,
        Kind.CONCLUSION,
    )


def _distinct(ctx: ValidationContext) -> Iterator[Consumption]:
    """Each input of each bound step, once per source: two parameters that receive the same
    variable from the same place are one problem, when there is one."""
    seen: set[tuple[str, str, str | None]] = set()
    for consumed in ctx.dataflow:
        key = (consumed.consumer.element.id, consumed.input.variable, consumed.input.by)
        if key not in seen:
            seen.add(key)
            yield consumed


def _unsupported(consumed: Consumption) -> str:
    """What a JP014 says of ``consumed``: who produces its variable, if not a supporter."""
    step, variable, by = consumed.consumer.step.name, consumed.input.variable, consumed.input.by
    named = consumed.reachable or consumed.producers
    ids = ", ".join(repr(p.element.id) for p in named)
    which = "which does not support it" if len(named) == 1 else "none of which supports it"
    if by is None:
        return f"{step} consumes {variable!r}, produced by {ids}, {which}"
    if consumed.within is not None and not consumed.reachable:
        return (
            f"{step} consumes {variable!r} by {by!r}, but no step at or below "
            f"{consumed.within.id!r} produces it"
        )
    return f"{step} consumes {variable!r} by {by!r}, produced by {ids}, {which}"


def _produced_below(bound: Binding, ctx: ValidationContext) -> Iterator[tuple[str, str]]:
    """Each variable the steps of ``bound``'s direct supporters produce, with its supporter."""
    for supporter in ctx.justification.supporters(bound.element.id):
        if (below := ctx.bindings.step_for(supporter.id)) is not None:
            for variable in below.produces:
                yield supporter.id, variable


def _evidence_without_use(bound: Binding, ctx: ValidationContext) -> bool:
    """Whether ``bound`` is an evidence step none of whose values any step consumes."""
    return bound.step.kind is Kind.EVIDENCE and not any(
        ctx.dataflow.users(bound.element.id, variable) for variable in bound.step.produces
    )


class DanglingTemplateChain(Rule):
    """The template chain the compiler wrote names an element the model does not have.

    jPipe 4.0.0 writes, beside a justification that implements a template, how it draws
    the templates (`implements`): which elements each template holds, and the `@support`s
    filled further down. Only the diagram reads it. The run reads the elements and the
    relations, which already are the whole argument. So a chain that names an element the
    model does not have, by its own id, is set aside rather than refusing an argument that
    runs: a diagram of it is drawn flat, as for a justification compiled by an earlier
    jPipe ([ADR-0029](adr/0029-the-runner-draws-the-dataflow.md)). The compiler writes a
    chain that matches the elements, so the warning says that the JSON file was edited, or
    written by something else, since it was compiled. As for every warning, a strict run
    counts it as an error.

    **Fix:** compile the justification again from its jPipe source. If the warning stays,
    report it to the jPipe compiler. Until then, only the diagram's template clusters are
    missing.
    """

    code = "JP026"
    severity = Severity.WARNING
    summary = "The template chain names an element that does not exist: it is not drawn."

    def check(self, ctx: ValidationContext) -> Iterator[Diagnostic]:
        if unknown := ctx.justification.unknown_in_template_chain:
            names = ", ".join(map(repr, unknown))
            which = "which is not an element" if len(unknown) == 1 else "none of which is one"
            yield self.diagnostic(
                f"the template chain names {names}, {which}, so a diagram of the argument "
                f"is drawn without its templates",
                fix="Compile the justification again from its source; if this stays, "
                "report it to jPipe.",
            )


RULES = RuleSet(
    [
        UnboundElement(),
        AmbiguousBinding(),
        ConflictingBinding(),
        RefinedElement(),
        MissingProducer(),
        UnconsumedOutput(),
        EvidenceProducesNothing(),
        StrategyIgnoresUpstreamOutput(),
        ConsumedBeforeProduced(),
        UnknownBindingTarget(),
        IncompatibleKind(),
        EvidenceObservesNothing(),
        AmbiguousConsumption(),
        DanglingTemplateChain(),
    ]
)
"""Every rule, run on every validation."""

RETIRED: Mapping[str, tuple[str, str]] = {
    "JP010": (
        "DuplicateProducer",
        "Several steps produced the same variable. Since 4.1.0, a consumed variable "
        "resolves among its consumer's supporters "
        "([ADR-0031](adr/0031-variables-resolve-among-supporters.md)): two producers of one "
        "name are an error only when one consumer can see both, which `JP025` reports.",
    ),
}
"""The codes no rule reports any more: for each, the rule's name and what replaced it."""
