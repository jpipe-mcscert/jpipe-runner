---
status: accepted
date: 2026-11-22
decision-makers: Sébastien Mosser
---

# ADR-0036: A step runs on the kind it was written for, as the element's origins say

## Context and Problem Statement

A step is declared with the kind of the element it implements: `@evidence`, `@strategy`,
`@sub_conclusion` or `@conclusion` ([ADR-0006](0006-one-decorator-per-kind.md)). Composition
changes kinds, and a step library is written against a model before anyone composes it, so
[ADR-0013](0013-kind-divergence-under-composition.md) decided a difference of kind **by the
pair of kinds alone**: `@evidence` or `@conclusion` on a sub-conclusion was a warning
(`JP008`), and the step ran; any other difference was an error (`JP016`). The provenance of
the element could not be read: `assemble` left no alias.

That accepted too much. `@evidence` on an element **written** as a sub-conclusion was a
warning, and ran: the sub-conclusion then observed files, and produced values the argument
above it consumed, outside what the model argues (#172).

Since jPipe 4.0.0 (jpipe-compiler#200), the JSON export gives each composed element its
**origins**: the element as it was in each model it was composed from, by its full id
there, with its kind there, nearest level first:

```json
{"id": "readiness:hook", "type": "sub-conclusion",
 "aliases": ["readiness:draft:tests", "readiness:tested:tested"],
 "origins": [{"model": "draft", "id": "draft:tests", "type": "evidence"},
             {"model": "tested", "id": "tested:tested", "type": "conclusion"}]}
```

An element that composition did not touch has origins too, with its own kind; an element
that composition created, such as `assemble`'s new conclusion, has none, and so does every
element of a model that was not composed. Compiling every composition in the test suite with
jPipe 4.0.0, including a refinement of a refinement, showed that an origin's id is always a
tail of one of the element's ids: `draft:tests` of the alias `readiness:draft:tests`, and,
two levels down, `tested:suite` of `top:mid:tested:suite`.

How should validation use the origins?

## Decision Drivers

- **Code runs only on an element of the kind it is declared with.** A step's signature is
  built for its kind.
- **Composing models never turns a library that ran into an error.** A library written
  against a source model keeps binding, and running, against every model composed from it.
- **The rule is decided from what the runner reads**: the compiler's JSON and the step
  library, without knowing how the compiler shortens ids.

## Considered Options

1. Keep ADR-0013: decide by the pair of kinds.
2. Decide by provenance: a difference of kind is excused when the step's id designates an
   origin of the element, and that origin had the step's kind; anything else is an error.
3. As 2, but keep ADR-0013's rule for a model without origins.

## Decision Outcome

Chosen option: **2, decide by provenance**, because it is the rule ADR-0013 wanted and could
not decide.

| A step bound to an element of another kind | Code | Severity |
|---|---|---|
| one of the step's ids designates an origin of the element, of the step's kind | `JP008` `RefinedElement` | warning |
| anything else | `JP016` `IncompatibleKind` | error |

- **A step designates an origin** by its id, or a strictly shorter tail of it, cut at `:`,
  as [ADR-0007](0007-binding-resolution.md) matches an id: the forms a library written
  against the origin's model uses. `@evidence("draft:tests")` on `readiness:hook` is the
  warning. An id that starts with the composed model's name was written against the composed
  model, where the element has its new kind, so it designates no origin:
  `@evidence("readiness:hook")`, `@evidence("readiness:draft:tests")` and, on an assembled
  model, `@conclusion("readiness:tested:tested")` are the error. The fix names the id the
  element had with the step's kind, `draft:tests`.
- **Binding does not change.** Since an origin's id is a tail of one of the element's ids,
  every id that designates an origin already designates the element, and an id that is a
  tail of origins of two elements is ambiguous (`JP006`) as it always was. Every origin is
  considered, at every level: under chained composition, a library written against any
  source model binds.
- **A step under the warning runs**, as before: after the argument below it, as an
  independent cross-check of the same claim, and only if that argument passed
  ([ADR-0021](0021-execution-semantics.md)). Setting it aside would leave the values it
  produces without a producer (`JP009`), which composition must not cause.
- **A model without origins** excuses nothing: every difference of kind is `JP016`. Such a
  model was either never composed, and then nothing changed a kind, or composed by a jPipe
  older than 4.0.0, and then recompiling it gives the origins; the fix of `JP016` says so on
  a model without origins, for the differences composition can make (an evidence or a
  conclusion turned into a sub-conclusion).
- **An origin of a kind no step implements**, such as a template's `abstract-support` that
  `refine` fills, is read and set aside: no step can have been written for it.
- **Two libraries that bind one element**, such as the draft's `@evidence("draft:tests")`
  and `tested`'s `@conclusion("tested:tested")` on the refined hook, are still a conflict
  (`JP007`): an element runs one step.

### Consequences

- Good, because a step written for a sub-conclusion's composed form, or for no form the
  element ever had, no longer runs on it.
- Good, because a library written against a source model still runs against every model
  composed from it, with one warning per element whose kind changed, and the warning names
  the origin the step was written for.
- Good, because the rule reads the compiler's contract, not its id prefixes.
- Bad, because a model composed by a jPipe older than 4.0.0, whose libraries ran with
  `JP008`, now stops with `JP016` until it is recompiled. jPipe 4.0.0 compiles the same
  models to the same ids.
- Bad, because the warning still cannot be silenced while the library also serves the source
  model, as ADR-0013 noted.
- Bad, because a tail shared by the origin's id and the composed id, such as `tested` for
  `readiness:tested:tested` and its origin `tested:tested`, cannot tell which model the step
  was written against, and is taken for the source's.

### Confirmation

- `tests/unit/validation/rules/test_refined_element.py` and `test_incompatible_kind.py`
  check every composition on jPipe 4.0.0's output (`refine`, `assemble`, unification, and a
  refinement of a refinement), a step bound by the composed id, and a model without origins.
- The `composed` and `unified` scenarios bind an `@evidence` to a sub-conclusion through an
  origin, and validation reports `JP008` and nothing else (`tests/unit/test_scenario_corpus.py`).

## Pros and Cons of the Options

### 1. Keep ADR-0013

- Good, because nothing changes.
- Bad, because `@evidence` and `@conclusion` run on any sub-conclusion, as #172 shows.

### 2. Decide by provenance

- Good, because it excuses exactly what composition changed.
- Bad, because models compiled before jPipe 4.0.0 must be recompiled.

### 3. Provenance, and ADR-0013 without origins

- Good, because no existing run breaks.
- Bad, because a model that was never composed has no origins either: the bug stays for every
  model that needs no composition, which are most of them.

## More Information

- #172 (this decision), jpipe-mcscert/jpipe-compiler#200 (origins in the JSON export).
- Supersedes [ADR-0013](0013-kind-divergence-under-composition.md).
