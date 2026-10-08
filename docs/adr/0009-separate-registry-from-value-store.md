---
status: accepted
date: 2026-10-08
decision-makers: Sébastien Mosser
---

# ADR-0009: Separate the declaration registry from the per-run value store

## Context and Problem Statement

A run needs two kinds of state: what the step library *declares* (which functions exist,
which elements they implement, what they consume and produce), and what the run
*produces* (the values its steps return). v3 kept both in one object, a module-level
singleton (`git show v3.6.0:src/jpipe_runner/framework/context.py`, line 245):

```python
ctx = RuntimeContext()  # module-level singleton — not thread-safe (see class docstring)
```

Its `_vars` mapped each function name to the variables it produced and consumed, with
their values in the same slots. Decorators filled it at import time, the engine read and
wrote it at run time. As a result:

- **Variable names were one flat, process-wide namespace.** `ctx.get(key)` scanned every
  function and returned the value of the first that mentioned `key`, and `ctx.set(key,
  value)` wrote only the first declaring slot, then returned.
- **`None` meant both "unset" and "produced `None`".** Declarations were registered with
  `None` as their value, so the engine logged an error when a consumed value was `None`,
  even when a step had legitimately produced it.
- **Import order was load-bearing.** Decorators had to have filled `ctx` before
  `PipelineEngine.load_config` ran, or configured keys matched nothing and vanished.
- **Nothing was ever reset.** `ctx` lived as long as the process, so a second run in the
  same interpreter, a test suite for example, saw the first run's declarations and values.

What structure should replace it (#117)?

## Decision Drivers

- **Two runs in one process share nothing.** Tests, notebooks and tools embedding the
  runner run it more than once.
- **A value says where it came from.** Reports, diagnostics and cross-checks need the
  element that produced each value.
- **"Nothing produced it" is distinct from every value.** `None` is a value a step may
  produce.
- **Declarations are static.** What a library declares does not change while it runs, and
  can be checked against the model before anything runs (#119).

## Considered Options

1. Keep one context object, created per run instead of per process.
2. Split it: a `StepRegistry` for declarations and a `ValueStore` for values, both per run.
3. No store: thread values through the engine as arguments and return values only.

## Decision Outcome

Chosen option: **2, split declaration from execution**, because it is the only option
where declarations can be checked before a run while values exist only during one, and
each has a single, typed job.

- **`StepRegistry`** (`jpipe_runner.steps`) holds `Step`s: kind, ids, consumes, produces,
  function. No values. Decorators do not fill it: each attaches its `Step` to the function
  (ADR-0006), and `StepRegistry.from_modules` collects them from the library's modules
  when a run starts. A registry filled at import time could not be rebuilt for a second
  run, because Python caches imported modules and does not run their decorators again.
- **`ValueStore`** (`jpipe_runner.values`) is created per run and owned by the engine
  (#120). It maps each variable to a `ProducedValue(value, produced_by)`, where `produced_by` is the
  id of the element whose step produced it. A variable is produced once; a second `put` is
  a `ValueError`, since validation rejects two producers before the run (JP010).
- **`UNSET`** is what `get` returns for a variable nothing has produced. It is the single
  member of the `Unset` enumeration, falsy, and never equal to `None`.
- **No module of the package holds either**, and no function rebinds module state.

### Consequences

- Good, because two runs in one process are independent by construction: each builds its
  registry and its store, and no module holds one.
- Good, because a value's provenance is recorded where it is stored, for the report (#122)
  and for diagnostics that name the producing element.
- Good, because a step that produces `None` is no longer reported as missing its input.
- Good, because the registry can be validated against the model (#115, #119) without
  executing anything.
- Bad, because the engine passes two objects where v3 reached for one global.
- Neutral, because variable names remain one namespace per run: a variable has one
  producer, which validation enforces, so a name designates one value without being
  qualified by its step.

### Confirmation

- `tests/unit/test_values.py` checks that a value carries its producer, that `UNSET` is
  not `None`, that two stores share nothing, that no module-level statement of the package
  builds a `ValueStore` or a `StepRegistry`, and that the package has no `global` or
  `nonlocal` statement.
- `tests/unit/test_steps.py` checks that two registries built from the same module are
  separate objects with the same steps.

## Pros and Cons of the Options

### 1. One context, per run

- Good, because it is the smallest change from v3.
- Bad, because declarations and values still share slots, so `None` still has two
  meanings, and declarations cannot be checked without creating the run's state.

### 2. Registry and store, per run

- Good, because each object has one job and a precise type.
- Good, because the registry is immutable, and the store is the only thing a run mutates.
- Bad, because it is two classes instead of one.

### 3. No store

- Good, because there is no mutable state at all.
- Bad, because a step's inputs come from several earlier steps, so the engine would
  rebuild the store's mapping in local variables, and lose provenance unless it carried it
  in the same way.

## More Information

- #117 (this decision), #114 and ADR-0006 (the decorators that attach a `Step`), #120 (the
  engine that owns a run's `ValueStore`), #122 (the JSON report that shows provenance).
- ADR-0008 dropped external variable injection, so every value in a store has a producing
  element.
