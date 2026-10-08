---
status: accepted
date: 2026-10-08
decision-makers: Sébastien Mosser
---

# ADR-0013: Kind divergence under composition is a warning, not an error

## Context and Problem Statement

A step declares the kind of the element it implements by its decorator: `@evidence`,
`@strategy`, `@sub_conclusion` or `@conclusion` (ADR-0006). The model says the element's
kind too. The two can disagree. Should validation (#119) treat every disagreement as an
error?

Most disagreements are mistakes. A `@strategy` bound to an evidence has the signature of
a strategy, consuming its supporters' values, on an element that has no supporters. But
composition also changes kinds, and a step library is usually written against a model
before anyone composes it. ADR-0007 makes such a library keep binding after composition,
through aliases and id tails, so the question arises for every composed model.

What composition does to kinds was checked on 2026-10-08 with jPipe 2.5.0, by compiling
real models (`jpipe process -i <file>.jd -m <model> -f JSON`) rather than reading the
operators' source:

| Operator | Model | What happens to kinds | Old ids |
|---|---|---|---|
| `refine` | `tests/e2e/scenarios/composed/refine.jd` | the hook evidence `draft:tests` and the refinement's conclusion `tested:tested` become the sub-conclusion `readiness:hook` | kept as aliases |
| `assemble` | `tests/unit/validation/fixtures/assemble.jd` (jpipe-examples' release example) | each source's conclusion becomes a sub-conclusion: `tested:tested` becomes `readiness:tested:tested` | prefixed, **no alias** |
| unification | `tests/unit/validation/fixtures/dominance.jd` | an evidence and a sub-conclusion with the same label merge into the sub-conclusion `release:unified_0` | kept as aliases |

The compiler's `Unifier.subsumes` states the rule behind the third row: a sub-conclusion
subsumes an evidence, and no other pair of distinct kinds is comparable. So composition
changes a kind in one direction only: an **evidence** or a **conclusion** becomes a
**sub-conclusion**. Nothing else.

## Decision Drivers

- **The intended workflow keeps working.** Someone writes a check against a model,
  someone else refines or assembles it, and the check still runs.
- **A genuine mistake stops the run.** A step whose signature is built for another kind
  of element is not run.
- **The rule is decidable from what the runner reads**: the compiler's JSON and the step
  library.
- **A change of kind is seen.** It changes what the step means, and should not pass
  silently.

## Considered Options

1. Every disagreement is an error.
2. Decide by the pair of kinds: evidence or conclusion bound to a sub-conclusion is a
   warning (`JP008`), anything else an error (`JP016`).
3. Decide by provenance: a warning only when the element was produced by composition from
   an element of the declared kind, as its aliases show.
4. Accept every disagreement silently.

## Decision Outcome

Chosen option: **2, decide by the pair of kinds**. It is the only option that keeps the
intended workflow running, refuses every disagreement composition cannot produce, and can
be decided from the JSON. Option 3 cannot be decided: `assemble` leaves no alias, so a
conclusion turned sub-conclusion by `assemble` looks exactly like one written as a
sub-conclusion.

| Step declared as | Element in the model | Code | Severity |
|---|---|---|---|
| `@evidence` or `@conclusion` | sub-conclusion | `JP008` `RefinedElement` | warning |
| any other kind than the element's | | `JP016` `IncompatibleKind` | error |

**Executing the cross-check needs no new machinery.** A refined hook keeps its
predecessors, so the bound step runs after the sub-argument below it. If the sub-argument
fails, the step is skipped by the usual propagation (M4). If it passes, the step runs and
may still fail: it is an independent cross-check of a claim that is also argued below it.
The step's own declaration is unchanged: an `@evidence` still consumes nothing and must
still produce a value someone consumes (`JP012`), and a `@conclusion` still produces
nothing.

### Consequences

- Good, because a step library written against a standalone model binds and runs against
  every model composed from it, with one warning per element whose kind changed.
- Good, because a `@strategy` on an evidence, or an `@evidence` on a strategy, stops the
  run.
- Bad, because a `@conclusion` bound to an element that was always a sub-conclusion is
  also a warning, not an error: the pair of kinds cannot tell it from an assembled
  conclusion. A test pins this limitation.
- Bad, because the warning cannot be silenced while the library also serves the source
  model, where the element still has its old kind. Declaring the step `@sub_conclusion`
  silences it for the composed model, and makes it `JP016` for the source model.

### Confirmation

- `tests/unit/validation/rules/test_refined_element.py` and `test_incompatible_kind.py`
  check every transition on the compiler's output, with steps written against the source
  models, and the genuine mistakes.
- The `composed` scenario binds an `@evidence` to the refined hook, and validation reports
  `JP008` and nothing else (`tests/unit/test_scenario_corpus.py`).

## Pros and Cons of the Options

### 1. Every disagreement is an error

- Good, because the rule is one comparison.
- Bad, because refining or assembling a model breaks every library written against its
  sources.

### 2. Decide by the pair of kinds

- Good, because it follows the only direction composition goes, and needs only the JSON.
- Bad, because it accepts with a warning a few mistakes that look like composition.

### 3. Decide by provenance

- Good, because it would be exact where aliases exist.
- Bad, because `assemble` leaves no alias, so it would reject assembled models' libraries.

### 4. Accept silently

- Good, because nothing breaks.
- Bad, because a step built for another kind of element runs, and a change of meaning
  goes unseen.

## More Information

- #119 (this decision), #116 and [ADR-0007](0007-binding-resolution.md) (the hook's id
  survives `refine`), [ADR-0006](0006-one-decorator-per-kind.md) (one decorator per kind).
- `jpipe-compiler`: `Unifier.subsumes` (dominance), `RefineOperator`, `AssembleOperator`.
