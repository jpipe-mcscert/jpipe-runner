---
status: accepted
date: 2026-10-09
decision-makers: Sébastien Mosser
---

# ADR-0021: Failures and skips propagate as skips; a step's mistakes fail its element

## Context and Problem Statement

M4 runs a validated step library against its model (#120). Validation already guarantees
a great deal: the model is acyclic (JP004), every evidence and strategy has a step
(JP005), and every consumed variable has one producer, which supports its consumer
(JP009, JP010, JP014). What remains to decide is what a run concludes:

- **What an element's status is** when its step passes, fails or skips; when it has no
  step; and when something it depends on did not pass. v3 had a special case: a step
  skipped with `@skip` did not stop what it supported, because `@skip` was evaluated when
  the module was imported, and its successors ran without the values it never produced.
- **What the justification's verdict is**, in particular when its conclusion is skipped.
  v3 exited 0 when nothing failed; the `skip_scenario` scenario expects the same.
- **What a step that misbehaves does to the run**: one that raises, returns something
  that is not an outcome (JP017), cannot see its artifacts (JP019, ADR-0019), or returns
  values other than those it declares. v3 flattened an exception to a string.

## Decision Drivers

- **No step is ever called with a value that does not exist.**
- **A reader can tell why an element did not pass**: its own check, or something below
  it, and which.
- **One mistake does not hide others**: the run goes on, as validation reports every
  problem (ADR-0010).
- **CI can trust the verdict**: a failure anywhere is a failure.
- **Deterministic**: the same library and artifacts give the same result.

## Considered Options

For propagation:

1. Failures and skips propagate alike, as skips (#120).
2. Failures propagate, a skip does not (v3).

For what a skipped element names:

1. The root causes: the elements upstream that did not pass on their own account.
2. The direct supporters that did not pass.

For a step's mistakes:

1. A diagnostic that fails the element, and the run goes on.
2. Stop the run.

## Decision Outcome

Chosen options: **failures and skips propagate as skips**, **blocked by their root
causes**, and **a step's mistakes are diagnostics that fail its element**, because only
they keep every call's inputs defined while saying, for each element, what stopped it.

**Statuses.** Elements are taken in topological order, ties broken by model order.

- If a supporter did not pass, the element is `SKIP`, its step is not called, and its
  `blocked_by` lists the elements upstream that failed or were skipped *on their own
  account*, in model order. Those are the roots: an element whose step was called had all
  its supporters pass, so nothing it depends on stopped it. A chain of five skipped
  elements names the one that started it, five times, not each its predecessor.
- Otherwise, a bound element's step is called, whatever the element's kind: a step bound
  to a refined sub-conclusion (JP008) runs after the argument below it, as a cross-check.
  `Pass` is `PASS`, `Fail` is `FAIL`, `Skip` is `SKIP` with an empty `blocked_by`.
- An unbound conclusion or sub-conclusion whose supporters all passed is `PASS`. One that
  nothing supports is `SKIP`, on its own account: nothing judged it.

**The verdict** is `FAIL` if an element failed, else `SKIP` if one was skipped, else
`PASS`; `INVALID` when validation reported an error and nothing ran. Since every element
supports the conclusion, `SKIP` means the conclusion is not established, and nothing
failed. The command line (M6) exits 0 for `PASS` and `SKIP`, as v3 did, 1 for `FAIL` and 3
for `INVALID`; `--strict` will also fail a `SKIP`.

**A step's mistakes** fail its element, with a diagnostic on its result, and the run goes
on; what the element supports is skipped, blocked by it:

| Code | When | Effect |
|---|---|---|
| `JP017` | the step returned something that is not an outcome | `FAIL` |
| `JP019` | an artifact it observes cannot be reached (ADR-0019) | `FAIL`, the step is not called |
| `JP022` `StepRaised` | the step raised an exception, or `SystemExit` | `FAIL`, the traceback is kept |
| `JP023` `DeclaredValueMissing` | `Pass` lacks a value the step declares | `FAIL`, nothing it returned is stored |
| `JP024` `UndeclaredValue` | `Pass` carries a value the step does not declare | warning: the value is dropped, the status stands |

The asymmetry between JP023 and JP024 follows from what each breaks. A missing declared
value would leave a consumer with nothing, so the step cannot be trusted. An undeclared
value has no consumer, since validation only lets a step consume a declared value, and
storing it could collide with another step's variable; dropping it changes nothing.

A traceback is kept as a `traceback.TracebackException`, structured and trimmed to the
step's frames, without the runner's or the frames' variables. `KeyboardInterrupt` stops
the run.

**The invariant is checked, not handled.** With validation passed, an element runs only
once every supporter passed, and a passing step stored every value it declares, so the
values it consumes exist. The engine raises a `RuntimeError`, a bug of the runner, rather
than pass `UNSET` to a step.

### Consequences

- Good, because no step is called with a value that was never produced: v3's skip let its
  successors run without one.
- Good, because a report can say "skipped: `release:e1` failed" for every element above
  `e1`, and a reader goes straight to the cause.
- Good, because every broken step of a run is reported in one run.
- Bad, because a step that skips stops everything above it, as a failure does. A check
  meant as optional must pass with what it found, rather than skip.
- Bad, because a skipped justification passes CI by default; `--strict` is needed to
  require that everything ran.

### Confirmation

- `tests/unit/test_engine.py` checks each status, each diagnostic and the verdict.
- `tests/unit/test_execution_properties.py` checks statuses, `blocked_by`, the calls and
  the verdict over generated models, against an oracle stated with `upstream` alone.
- `tests/unit/test_scenario_corpus.py` pins each scenario's verdict and the elements that
  did not pass, until the golden reports do (#124).

## Pros and Cons of the Options

### Propagation: failures and skips alike

- Good, because a step never runs without its inputs.
- Bad, because a skip cannot be used to mean "optional".

### Propagation: v3, a skip does not propagate

- Good, because it is what v3 users know.
- Bad, because a successor runs without the values the skipped step did not produce: v3's
  rule only held because `@skip` was decided at import time.

### Blocked by the root causes

- Good, because it names what to fix.
- Neutral, because the direct supporters remain in the model, for a reader who wants the
  path.

### Blocked by the direct supporters

- Good, because it is local.
- Bad, because in a deep argument it names an element that was itself only skipped.

### A step's mistakes stop the run

- Good, because nothing runs after a broken step.
- Bad, because one broken step hides every other, and the elements that do not depend on
  it are not judged.

## More Information

- #120 (this decision), #144; [ADR-0005](0005-outcomes-as-return-values.md), outcomes;
  [ADR-0010](0010-diagnostics-as-data-rules-as-objects.md), diagnostics;
  [ADR-0013](0013-kind-divergence-under-composition.md), cross-checks;
  [ADR-0019](0019-evidence-observes-files.md), observed artifacts.
