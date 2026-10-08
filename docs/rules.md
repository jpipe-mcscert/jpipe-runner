# Diagnostic codes

<!-- Generated from src/jpipe_runner/rules.py by `poetry run pytest --update-goldens`. Do not edit. -->

Every problem the runner reports is a diagnostic with a code, `JPnnn`, which never changes
meaning. Its message is written for humans and may be reworded, so scripts and tests rely
on the code.

## Validation rules

Before running anything, the runner checks the step library against the model with the
rules below, and reports every problem it finds at once
([ADR-0010](adr/0010-diagnostics-as-data-rules-as-objects.md)).

- An **error** stops the run: no step executes.
- A **warning** is reported, and the run continues. A strict run counts warnings as errors.

No rule can be disabled.

| Code | Rule | Severity | Reports |
|---|---|---|---|
| [JP006](#jp006-ambiguousbinding) | `AmbiguousBinding` | error | An id designates several elements. |
| [JP007](#jp007-conflictingbinding) | `ConflictingBinding` | error | An element is bound by several steps, or a step to several elements. |
| [JP015](#jp015-unknownbindingtarget) | `UnknownBindingTarget` | error | An id designates no element of the model. |

### JP006 `AmbiguousBinding`

**error**: An id designates several elements.

A step's id is a tail of the ids of several elements, so it designates none of them.

An id designates an element when it is the element's id or one of its aliases, that id
qualified by the justification's name, or a strictly shorter tail of either, cut at
`:` ([ADR-0007](adr/0007-binding-resolution.md)). An exact match always wins. A tail that
ends the ids of two elements is not resolved to either: the runner never guesses which
element a step implements. A tail unique today can become ambiguous when the model
grows, or is composed with another.

**Fix:** use a longer id, which designates one element, such as the id the compiler
exports.

### JP007 `ConflictingBinding`

**error**: An element is bound by several steps, or a step to several elements.

An element is bound by several steps, or a step's ids designate several elements.

Binding is one to one: an element is implemented by at most one function, and a
function implements exactly one element. Two functions for one claim would give it two
verdicts; one function for two claims would produce its variables twice. The element
or the step in conflict is left unbound.

After `refine`, the hook and the refinement's conclusion are one element, which
answers to both ids: binding both is a conflict, not a cross-check.

**Fix:** keep one function per element. When two elements are checked the same way,
share the code in a helper, not the step.

### JP015 `UnknownBindingTarget`

**error**: An id designates no element of the model.

A step's id designates no element of the model, so the step would never run.

v3 ignored such an id silently: a typo meant the check was never run, and nothing said
so. The step's other ids may still bind it.

**Fix:** use the id of an element of the model, as the compiler exports it, or a unique
tail of it.

## Codes reported outside validation

These are errors. A model that cannot be loaded is not validated, and a step that
returns anything other than an outcome fails.

| Code | Name | Reported when | Reports |
|---|---|---|---|
| JP001 | `SchemaConformance` | loading the model | The file is not UTF-8 JSON in the compiler's format, or is a template. |
| JP002 | `UniqueElementId` | loading the model | An id or alias designates several elements. |
| JP003 | `RelationEndpointsExist` | loading the model | A relation names an element that does not exist. |
| JP004 | `Acyclic` | loading the model | The relations form a cycle: an element supports itself, directly or not. |
| JP017 | `NotAnOutcome` | running a step | A step returned something other than `Pass`, `Fail` or `Skip`. |
