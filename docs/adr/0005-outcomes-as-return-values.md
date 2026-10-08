---
status: accepted
date: 2026-10-08
decision-makers: Sébastien Mosser
---

# ADR-0005: Outcomes as return values instead of a `produce` callable

## Context and Problem Statement

A step tells the runner two things: whether its check holds, and which values it produces
for the steps it supports. In v3 (`git show v3.6.0:src/jpipe_runner/framework/decorators/jpipe_decorator.py`)
these went through two channels:

- **The verdict was a `bool`.** The engine raised a `FunctionException` on `False` and on
  anything that was not a `bool` (`engine.py`, around line 716). A step could not say "I
  cannot judge this here", so v3 added a separate `@skip` decorator. It was evaluated at
  import time, before the step could look at anything.
- **Values went through an injected `produce(name, value)` callable.** `@jpipe(produce=[…])`
  required the function's *last* parameter to be named `produce` (`_check_produce_param`),
  wrapped the function to inject it, and checked after the call that every declared
  variable had been produced. A function that declared nothing still received a no-op
  `produce` if it had the slot.
- **Consumed values were policed by an AST pass.** `ConsumedVariableChecker` parsed the
  function's source with `inspect.getsource` and rejected a declared variable that the body
  never read by name. It fails on functions whose source is not available, and its notion
  of "read" is a `Name` node in load context anywhere in the body.

The jPipe compiler generates the skeleton of these functions (`PythonExporter.java`), with
`produce: JpipeProduce` as the parameter and `-> bool` as the return type. The authoring
API is rewritten in v4 (#113, #114). How should a step report its verdict and its values?

## Decision Drivers

- **One channel.** The verdict and the values belong to the same event, the step's
  completion, and should not be able to disagree.
- **A step is a plain function.** It can be called in a unit test with ordinary arguments,
  without the runner, and nothing is injected that the test must fake.
- **Three verdicts, decided at run time.** "Holds", "does not hold" and "cannot be judged
  here" are all results of looking at the world, so all three come from the step's body.
- **Reasons travel with failures.** A failure report says why, in the step's own words.
- **v3 users are told what changed.** The first v3 habit a migrating user hits must produce
  a message that names the v4 replacement, not a type error.

## Considered Options

1. Keep v3: a `bool` verdict and an injected `produce` callable.
2. Return the produced values (a `dict`) and raise an exception to fail.
3. Return an outcome: `Pass(values)`, `Fail(reason)` or `Skip(reason)`.

## Decision Outcome

Chosen option: **3, return an outcome**, because it is the only option where the verdict
and the values are one object returned by a plain function, and where skipping is a
result rather than a decorator.

```python
Pass(values: Mapping[str, Any] = {}, /, **kwargs)   # Pass(), Pass({"a": 1}), Pass(a=1)
Fail(reason: str)
Skip(reason: str = "")
```

- `Outcome` is the base class, and is not instantiated itself. All outcomes are frozen
  dataclasses. `Pass.values` is a read-only copy of what it was given.
- The mapping argument of `Pass` is positional-only, so every name, including `values`, can
  be passed as a keyword. A name given both ways is a `TypeError`.
- A step that returns anything else is reported with a new diagnostic code, **JP017
  `NotAnOutcome`** (error), by `as_outcome(returned, element_id)`. The codes JP001 to JP016
  are allocated by #119, so JP017 is the next one. Its `fix` names the replacement:
  `Pass()` for `True`, `Fail(reason)` for `False`, `Pass(values)` for a mapping, and the
  three outcomes otherwise (`None` usually means a missing `return`).
- There is no `produce` parameter, no rule about the last parameter's name, and no AST pass.
  What a step produces and consumes is declared by its decorator (#114, ADR-0006); the
  engine (#120) compares that declaration with the values in `Pass`.

### Consequences

- Good, because a step is a plain function: a unit test calls it and compares its result
  with `Pass(coverage=92.0)`, since outcomes compare by value.
- Good, because a failure carries its reason, and `Skip` is decided at run time, by the
  step, from what it observes. `@skip` is dropped (#114).
- Good, because the verdict and the values cannot disagree: a failing step produces nothing.
- Good, because the function's source is never parsed, so steps defined in a REPL, by a
  decorator factory or in a compiled module work.
- Bad, because every v3 step changes: its signature (no `produce`), its body (no
  `produce(…)` calls) and its returns. The JP017 fix messages and the migration guide (#129)
  carry that cost; v4 is a breaking release in any case (ADR-0002).
- Bad, because the compiler's generated skeletons must change in step (#140).
- Neutral, because a step that raises still fails: the engine reports the exception as a
  FAIL of that step, with its traceback (#120).

### Confirmation

- `tests/unit/test_outcomes.py` pins the constructors, immutability, equality, and JP017
  with its fix for `True`, `False`, `None`, a mapping and other values.
- `tests/unit/test_scenario_corpus.py` checks that the e2e step libraries import only the
  public API, which has no `produce` and no `@skip`.

## Pros and Cons of the Options

### 1. Keep v3

- Good, because existing step libraries keep working.
- Bad, because the verdict and the values travel separately, and the runner must check
  after the fact that they agree.
- Bad, because a parameter is injected by name and position, so a step cannot be called
  without faking it, and there is no "cannot judge" verdict.

### 2. Return values, raise to fail

- Good, because it is plain Python.
- Bad, because a failing check then looks like a crashing one: both are exceptions, and
  the report shows a traceback where a reason belongs.
- Bad, because skipping needs a third mechanism, such as another exception type.

### 3. Return an outcome

- Good, because the three verdicts are three types, and the values are part of `Pass`.
- Good, because the return type `-> Outcome` documents the contract, for readers and for
  type checkers.
- Bad, because it is three new names to learn, exported from `jpipe_runner`.

## More Information

- #113 (this decision), #114 (the decorators that declare what a step produces and
  consumes), #120 (execution), #126 (authoring docs).
- #140 tracks the compiler's Python exporter, which generates v3 skeletons until it is
  ported at the 4.0.0 release.
