---
status: accepted
date: 2026-10-08
decision-makers: Sébastien Mosser
---

# ADR-0006: One decorator per kind

## Context and Problem Statement

A step library tells the runner which function implements which element of the model, and
what each function consumes and produces. v3 (`git show v3.6.0:src/jpipe_runner/framework/decorators/`)
spread this over four decorators that a function stacked:

- `@jpipe(consume=[…], produce=[…])` declared the dataflow, and wrapped the function to
  inject arguments and a `produce` callable (ADR-0005).
- `@jpipe_link("id")`, once per id, bound the function to an element. It was added late:
  before it, a function was found by the *sanitized label* of its element, so rewording a
  label broke the binding.
- `@skip(condition, reason)` recorded, at import time, that a function should not run.
- `@contribution(positive=[…], negative=[…])` recorded contributions in the global context.
  It had no test and no documentation, and nothing in the runner read it back.

None of these said what *kind* of element the function implemented. A function could
declare `consume=[…]` and be bound to an evidence, which by definition observes the world
rather than consuming another step's output, and nothing noticed. Each decorator also wrote
into the module-level `ctx` singleton (ADR-0009), and each wrapped the function with
`@wraps`, so their behaviour depended on the order they were stacked in.

The jPipe compiler generates the skeleton of a step library (`PythonExporter.java`): one
`@jpipe_link` per id the element is known by, then `@jpipe(...)` with arguments chosen by
kind (`produce` only for evidence, `consume` only for a conclusion). What should the v4
declaration look like (#114)?

## Decision Drivers

- **The code says what the model says.** A reader of a step library sees which kind of
  element each function implements, and a step that disagrees with the model can be
  reported (JP008 and JP016, #119).
- **Impossible declarations cannot be written.** Evidence consumes nothing, and a
  conclusion, being terminal, produces nothing.
- **A step is a plain function.** Declaring it does not wrap it, inject into it or register
  it anywhere global, so it can be called in a test and collected afresh by every run.
- **One function, several ids.** Composition gives an element several ids, and the
  compiler emits each of them (ADR-0007), so a declaration takes one or many.
- **Close to what the compiler generates.** The exporter must change for v4 anyway (#140);
  the closer the new shape is to the old, the smaller that change.

## Considered Options

1. Keep `@jpipe` and `@jpipe_link`, and add a `kind=` argument.
2. One generic decorator, `@step(kind, *ids, consumes=…, produces=…)`.
3. One decorator per kind: `@evidence`, `@strategy`, `@sub_conclusion`, `@conclusion`.

## Decision Outcome

Chosen option: **3, one decorator per kind**, because it is the only option where the
signature of the declaration itself rules out what a kind cannot do.

| Decorator | Signature | |
|---|---|---|
| `@evidence` | `(*ids, produces=())` | no `consumes`: evidence observes the world |
| `@strategy` | `(*ids, consumes=(), produces=())` | |
| `@sub_conclusion` | `(*ids, consumes=(), produces=())` | optional: an unbound one derives its status |
| `@conclusion` | `(*ids, consumes=())` | no `produces`: terminal; optional likewise |

- **Ids are positional**, one or many: `@evidence("rigor:r17:e_metric", "rigor:r18:e")`.
  `@jpipe_link` disappears.
- **A decorator registers nothing.** It attaches a frozen `Step` (kind, ids, consumes,
  produces, function) to the function and returns the function itself. A `StepRegistry`
  collects the steps from the library's modules for a run (ADR-0009).
- **The function's parameters are its consumed variables**, passed by keyword. A
  parameter that is not consumed, or a consumed variable with no parameter to receive it,
  is a `TypeError` when the module is imported, checked with `inspect.signature`. A
  parameter with a default, or `**kwargs`, is allowed.
- **Other mistakes visible in the declaration** are a `TypeError` at import too: no id, an
  empty id, an id or a variable given twice, a bare string where a list of variables is
  expected (`produces="x"`), a variable name that is not a Python identifier, the
  decorator used without its parentheses, or a second step decorator on one function.
- **Faults that depend on the model are not checked here.** Whether an id designates an
  element is binding resolution (#115); whether the dataflow holds, including a step that
  consumes what it produces, is validation (#119).
- **`@skip` is dropped.** A step returns `Skip(reason)`, decided at run time (ADR-0005).
- **`@contribution` is dropped.** It had no test, no documentation and no reader.
- **The package root is the public API.** `jpipe_runner` exports the four decorators,
  `Outcome`, `Pass`, `Fail`, `Skip` and `__version__`. Importing `jpipe_runner.framework`,
  where the v3 decorators lived and where every generated v3 library imports from, raises
  an `ImportError` that says what replaced them.

### Consequences

- Good, because the kind is visible in the code, so the runner can compare it with the
  model, and composition's kind changes become a reported, explained warning (JP008).
- Good, because "produced but never consumed" can always be satisfied: the conclusion can
  consume the last strategy's output. In v3 that rule was fatal and forced practitioners to
  write functions that did nothing but consume.
- Good, because a step is a plain function: no wrapper, no stacking order, no injection.
- Good, because the compiler's change is local: its link list becomes the positional ids,
  and its kind-dependent `@jpipe` arguments become the decorator's keywords (#140).
- Bad, because every v3 library is rewritten. The `ImportError` from
  `jpipe_runner.framework` makes the first failure say so.
- Bad, because a `TypeError` at import stops the library from loading, so the run reports
  only the first faulty declaration in a module. Those faults are visible in the
  declaration alone, and the message names the function.
- Good, because a user's own decorator stacked above a step decorator keeps working: the
  `functools.wraps` it uses copies the declaration onto the wrapper, and the run calls the
  wrapper, the function the module exposes.

### Confirmation

- `tests/unit/test_steps.py` pins each decorator's signature and its `TypeError`s, the
  `Step` it attaches, and the `ImportError` of `jpipe_runner.framework`.
- `tests/unit/test_scenario_corpus.py` imports every e2e step library and checks that the
  registry holds exactly its decorated functions, and that libraries import nothing from
  `jpipe_runner` but the public API.

## Pros and Cons of the Options

### 1. `@jpipe` and `@jpipe_link`, plus `kind=`

- Good, because v3 libraries need the least change.
- Bad, because `kind=` is optional by nature of an added argument, and evidence could
  still declare `consume=[…]`.
- Bad, because binding and dataflow stay in two decorators that must be stacked together.

### 2. One generic `@step(kind, …)`

- Good, because there is one name to learn.
- Bad, because its signature is the union of all kinds', so `consumes` on evidence and
  `produces` on a conclusion are written and caught only by a run-time check.

### 3. One decorator per kind

- Good, because the declaration reads as the model does: `@evidence("release:e1")`.
- Good, because what a kind cannot do cannot be written.
- Bad, because there are four names instead of one.

## More Information

- #114 (this decision), #115 and ADR-0007 (binding), #117 and ADR-0009 (the registry),
  #119 (JP008 and JP016, kind divergence).
- ADR-0008 drops external variable injection, decided in the same ticket.
- #140 tracks porting the compiler's Python exporter to these decorators.
