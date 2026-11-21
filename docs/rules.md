# Diagnostic codes

<!-- Generated from src/jpipe_runner/rules.py by `poetry run pytest --update-goldens`. Do not edit. -->

Every problem the runner reports is a [diagnostic](concepts.md#diagnostic) with a code,
`JPnnn`, which never changes meaning. Its message is written for humans and may be
reworded, so scripts and tests rely on the code.

## Validation rules

Before running anything, the runner checks the step library against the model with the
rules below, and reports every problem it finds at once
([ADR-0010](adr/0010-diagnostics-as-data-rules-as-objects.md)).

- An **error** stops the run: no step executes.
- A **warning** is reported, and the run continues. A strict run counts warnings as errors.

No rule can be disabled.

| Code | Rule | Severity | Reports |
|---|---|---|---|
| [JP005](#jp005-unboundelement) | `UnboundElement` | error | An evidence or a strategy has no step. |
| [JP006](#jp006-ambiguousbinding) | `AmbiguousBinding` | error | An id designates several elements. |
| [JP007](#jp007-conflictingbinding) | `ConflictingBinding` | error | An element is bound by several steps, or a step to several elements. |
| [JP008](#jp008-refinedelement) | `RefinedElement` | warning | A step declared as evidence or conclusion is bound to a sub-conclusion. |
| [JP009](#jp009-missingproducer) | `MissingProducer` | error | A step consumes a variable that no step produces. |
| [JP011](#jp011-unconsumedoutput) | `UnconsumedOutput` | warning | A step produces a variable that no step consumes. |
| [JP012](#jp012-evidenceproducesnothing) | `EvidenceProducesNothing` | error | An evidence produces no value that another step consumes. |
| [JP013](#jp013-strategyignoresupstreamoutput) | `StrategyIgnoresUpstreamOutput` | warning | A strategy ignores a value its supporters produce for another step. |
| [JP014](#jp014-consumedbeforeproduced) | `ConsumedBeforeProduced` | error | A step consumes a variable that no step supporting it produces. |
| [JP015](#jp015-unknownbindingtarget) | `UnknownBindingTarget` | error | An id designates no element of the model. |
| [JP016](#jp016-incompatiblekind) | `IncompatibleKind` | error | A step's kind differs from its element's, in a way composition cannot explain. |
| [JP018](#jp018-evidenceobservesnothing) | `EvidenceObservesNothing` | error | An evidence observes no artifact. |
| [JP025](#jp025-ambiguousconsumption) | `AmbiguousConsumption` | error | Several steps that support a step produce a variable it consumes. |
| [JP026](#jp026-danglingtemplatechain) | `DanglingTemplateChain` | warning | The template chain names an element that does not exist: it is not drawn. |

### JP005 `UnboundElement`

Severity: **error**.

An evidence or a strategy of the model has no step.

Evidence and strategies are where an argument is checked: an evidence's step observes
the world, a strategy's judges what its supporters found. Without a step, the claim
they stand for would be accepted unchecked. Conclusions and sub-conclusions are
optional: an unbound one takes its status from what supports it. An element left
unbound by a conflict, claimed by several steps or designated by a step whose ids
designate several elements, is reported by `JP007` instead.

**Fix:** write its step, `@evidence("id")` or `@strategy("id")`.

### JP006 `AmbiguousBinding`

Severity: **error**.

A step's id is a tail of the ids of several elements, so it designates none of them.

An id designates an element when it is the element's id or one of its aliases, that id
qualified by the justification's name, or a strictly shorter tail of either, cut at
`:` ([ADR-0007](adr/0007-binding-resolution.md)). An exact match always wins. A tail that
ends the ids of two elements is not resolved to either: the runner never guesses which
element a step implements. A tail unique today can become ambiguous when the model
grows, or is composed with another. The id a step gives as `by`, in
`Produced(variable, by=id)`, designates an element in the same way.

**Fix:** use a longer id, which designates one element, such as the id the compiler
exports.

### JP007 `ConflictingBinding`

Severity: **error**.

An element is bound by several steps, or a step's ids designate several elements.

Binding is one to one: an element is implemented by at most one function, and a
function implements exactly one element. Two functions for one claim would give it two
verdicts; one function for two claims would produce its variables twice. The element
or the step in conflict is left unbound.

After `refine`, the hook and the refinement's conclusion are one element, which
answers to both ids: binding both is a conflict, not a cross-check.

**Fix:** keep one function per element. When two elements are checked the same way,
share the code in a helper, not the step.

### JP008 `RefinedElement`

Severity: **warning**.

A step declared as evidence or conclusion is bound to what the model calls a
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

### JP009 `MissingProducer`

Severity: **error**.

A step consumes a variable that no step produces.

Every value a step receives is produced by another step: there is no other source
([ADR-0008](adr/0008-drop-external-variable-injection.md)). A step that binds no
element never runs, so what it declares does not count.

**Fix:** produce the variable in a step that supports the consumer, or remove it from
`consumes` and from the function's parameters.

### JP011 `UnconsumedOutput`

Severity: **warning**.

A step produces a variable that no step consumes.

A value nothing reads is either computed for nothing, or meant for a step that forgot
to consume it. An evidence that produces nothing anyone consumes is reported by
`JP012` instead.

**Fix:** consume the variable where it is needed, or stop producing it.

### JP012 `EvidenceProducesNothing`

Severity: **error**.

An evidence step produces no value that another step consumes.

Evidence observes the world and reports what it observed, as values, for the
strategies above it to judge. An evidence that only passes or fails hands its
strategy a verdict without the facts behind it, and a strategy cannot reason about
what it is not given. Placeholder steps (`return Pass()`) are the usual cause.

**Fix:** produce what the evidence observed (a count, a measure, a version), and
consume it in the strategy that judges it.

### JP013 `StrategyIgnoresUpstreamOutput`

Severity: **warning**.

A strategy does not consume a variable that one of its supporters produces for
another step.

A strategy is the reasoning that turns what its supporters found into a claim. A value
produced right below it and read only further up skips that reasoning: the strategy
judges without looking at it. A value nobody consumes is reported by `JP011` or
`JP012` instead. A value counts as read further up when a step above draws on that
supporter's value, not merely on a variable of the same name.

**Fix:** consume the variable in the strategy, or produce it where it is used.

### JP014 `ConsumedBeforeProduced`

Severity: **error**.

A step consumes a variable that no step supporting it produces.

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

### JP015 `UnknownBindingTarget`

Severity: **error**.

A step's id designates no element of the model, so the step would never run.

v3 ignored such an id silently: a typo meant the check was never run, and nothing said
so. The step's other ids may still bind it. The id a step gives as `by`, in
`Produced(variable, by=id)`, must designate an element too: otherwise, nothing says
which value the step receives.

**Fix:** use the id of an element of the model, as the compiler exports it, or a unique
tail of it.

### JP016 `IncompatibleKind`

Severity: **error**.

A step's decorator declares a kind that its element cannot have become by
composition.

Composition only ever turns an evidence or a conclusion into a sub-conclusion
(`JP008`). Any other difference between a step's kind and its element's, such as a
`@strategy` bound to an evidence, is an authoring mistake: the step's signature is
built for another kind of element.

**Fix:** use the decorator of the element's kind, or bind the step to the element it
was written for.

### JP018 `EvidenceObservesNothing`

Severity: **error**.

An evidence step declares no artifact that it observes.

Evidence is where an argument touches the world: a test report, a changelog, a
configuration file. An evidence that observes nothing checks nothing in the world,
whatever it returns. Placeholder steps (`return Pass()`) and skeletons left unfilled
are the usual cause. In an assurance case, fake evidence is worse than missing
evidence: it looks like a check. Declaring the artifacts also lets the runner check
that they exist, record them, and archive them with the report
([ADR-0018](adr/0018-evidence-declares-observed-artifacts.md)).

**Fix:** declare what the evidence observes, and take it as a parameter:
`@evidence("id", observes={"changelog": "CHANGELOG.md"})`.

### JP025 `AmbiguousConsumption`

Severity: **error**.

Several steps that support a step produce a variable it consumes.

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

### JP026 `DanglingTemplateChain`

Severity: **warning**.

The template chain the compiler wrote names an element the model does not have.

jPipe 4.0.0 writes, beside a justification that implements a template, how it draws
the templates (`implements`): which elements each template holds, and the `@support`s
filled further down. Only the diagram reads it. The run reads the elements and the
relations, which already are the whole argument, so a chain that does not match them
is set aside rather than refusing an argument that runs: the diagram draws it flat, as
for a justification compiled by an earlier jPipe
([ADR-0029](adr/0029-the-runner-draws-the-dataflow.md)). A chain that names an
unknown element is not the compiler's usual output, so it is reported.

**Fix:** compile the justification again, with jPipe 4.0.0 or later. If the warning
stays, report it to the jPipe compiler. Until then, the run is unaffected: only the
diagram's template clusters are missing.

## Codes reported outside validation

A model or a step library that cannot be loaded is not validated, and nothing runs.
While the steps run, an error fails the element it is about, and the run goes on:
what that element supports is skipped. A warning is reported, and changes nothing
else.

| Code | Name | Severity | Reported when | Reports |
|---|---|---|---|---|
| JP001 | `SchemaConformance` | error | loading the model | The file is not UTF-8 JSON in the compiler's format, or is a template. |
| JP002 | `UniqueElementId` | error | loading the model | An id or alias designates several elements. |
| JP003 | `RelationEndpointsExist` | error | loading the model | A relation names an element that does not exist. |
| JP004 | `Acyclic` | error | loading the model | The relations form a cycle: an element supports itself, directly or not. |
| JP017 | `NotAnOutcome` | error | running a step | A step returned something other than `Pass`, `Fail` or `Skip`. |
| JP019 | `UnreachableArtifact` | error | running a step | An artifact an evidence observes is missing, unreadable or not a regular file, or a glob matches no file: the step is not called. |
| JP020 | `LibraryImportFailed` | error | importing the libraries | A step library raised an exception when it was imported. |
| JP021 | `UnusableLibraryName` | error | importing the libraries | A library's file name cannot be its module's name: another library or module has it, or it is not a Python identifier. |
| JP022 | `StepRaised` | error | running a step | A step raised an exception. The traceback is kept. |
| JP023 | `DeclaredValueMissing` | error | running a step | A step returned `Pass` without a value it declares it produces: nothing it returned is kept. |
| JP024 | `UndeclaredValue` | warning | running a step | A step returned `Pass` with a value it does not declare: the value is dropped, and the step keeps its status. |

## Retired codes

A code never changes meaning, so a code no rule reports any more is retired, and
never reused.

| Code | Name | Why |
|---|---|---|
| JP010 | `DuplicateProducer` | Several steps produced the same variable. Since 4.1.0, a consumed variable resolves among its consumer's supporters ([ADR-0031](adr/0031-variables-resolve-among-supporters.md)): two producers of one name are an error only when one consumer can see both, which `JP025` reports. |
