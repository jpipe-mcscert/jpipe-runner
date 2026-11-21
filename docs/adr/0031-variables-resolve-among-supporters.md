---
status: accepted
date: 2026-11-21
decision-makers: Sébastien Mosser
---

# ADR-0031: A consumed variable resolves among its consumer's supporters

## Context and Problem Statement

A step declares the variables it consumes and produces by name
([ADR-0006](0006-one-decorator-per-kind.md)). Today a run has a single namespace for these
names: `JP010 DuplicateProducer` refuses any model in which two bound steps produce the
same variable, wherever they are in the argument. The `ValueStore` holds each value under
its bare name, and so does the dataflow diagram, which draws one node per variable name
([ADR-0029](0029-the-runner-draws-the-dataflow.md)).
[ADR-0009](0009-separate-registry-from-value-store.md) accepted this as neutral, since
validation guaranteed a single producer.

This is a problem for step libraries written by independent developers. jPipe composes
models (`assemble`, `refine`), and a library written against a standalone source model
keeps binding after composition ([ADR-0007](0007-binding-resolution.md)). But its
variables only work if their names differ from those of every other library in the same
composition. Library A argues *the code is tested*: its evidence produces `coverage`,
and its strategy consumes it. Library B argues *the documentation is complete*, with its
own `coverage`. Each library is valid against its own model. Once the two models are
assembled, the run fails JP010. Neither author did anything wrong, and the integrator can
only fix it by editing a library they do not own.

The repository's own scenarios show the workaround authors use today.
`tests/e2e/scenarios/assembled/documented_steps.py` names its value `documented_release`,
its docstring says, "so that it cannot clash with a variable of `tested` once the two
models run together (JP010)". That scenario lists "distinct … variable names (JP010)
across libraries" as one of the things it exercises. The authors coordinated their names,
which independent authors cannot do.

The argument already scopes the dataflow. `JP014 ConsumedBeforeProduced` requires that a
consumed value's producer supports its consumer, directly or not: a step runs after its
supporters, and is skipped when one of them fails or is skipped
([ADR-0021](0021-execution-semantics.md)). So a step can only ever receive a value from
its own supporters. A producer elsewhere in the model can never reach it, yet it still
counts as a conflict. How should a consumed variable designate its value, so that
libraries written apart can run together (#187)?

## Decision Drivers

- **Libraries written apart run together unchanged.** Assembling a library its integrator
  does not own must not require editing it.
- **Every library valid today stays valid**, and each of its consumed variables resolves
  to the same producer. The authoring API is co-owned with the compiler's
  `PythonExporter`, and the report is a contract with jpipe-ci-actions
  ([ADR-0011](0011-json-report-is-the-machine-readable-contract.md)).
- **Nothing resolves by guess.** As with ids ([ADR-0007](0007-binding-resolution.md)), a
  name that could designate two values is an error, not a choice. In an assurance case,
  which value a step receives must be visible to its author.
- **The model shows the dataflow.** Every value comes from a step bound to an element of
  the model. No configuration file or command-line option becomes a source of values
  ([ADR-0008](0008-drop-external-variable-injection.md)).
- **Ambiguity is fixed by the author who creates it.** When two values could reach one
  step, it is that step's author who knows which one they mean.

## Considered Options

1. Scope a consumed variable by the argument graph: it resolves among its consumer's
   supporters.
2. Qualify a variable by the model its producer came from.
3. Qualify a variable by the library (Python module) that produces it.
4. Rename variables at assembly time, with a mapping file or a command-line option.
5. Keep one namespace, and ask every library to prefix its names.

## Decision Outcome

Chosen option: **1, scope a consumed variable by the argument graph**, because it is the
only option under which libraries written apart run together unchanged. It also uses the
argument's own structure rather than a new boundary, and leaves every valid library
resolving as it does today.

### Resolution

A step bound to an element *C* consumes a variable *n*. Its **candidates** are the bound
steps that produce *n* and whose elements support *C*, directly or not
(`Justification.upstream`). There must be exactly one candidate, and that producer's value
is what the step receives.

Two producers of one name are no longer an error in themselves. They are an error only
when both are candidates for the same consumption. A nearer producer does **not** shadow a
farther one: graph distance is not something the author of a step can see when reading it,
so a conflict is never resolved by it.

### Naming the producer

A step whose consumption is ambiguous names the producer it means. `consumes` keeps its
list form, and also accepts a mapping from each parameter to its source. This mirrors
`observes` ([ADR-0028](0028-observables-and-file-relative-paths.md)). A source is either a
variable name, resolved as above, or `Produced(variable, by=id)`, where `id` designates
an element by the rules of [ADR-0007](0007-binding-resolution.md), and the candidates are
narrowed to that element and its supporters:

<!-- fmt:off -->
```python
from jpipe_runner import Fail, Outcome, Pass, Produced, strategy

@strategy(
    "readiness:assembleStrategy",
    consumes={
        "tests": Produced("coverage", by="tested:tested"),
        "docs": Produced("coverage", by="documented:documented"),
    },
)
def all_release_gates_pass(tests: float, docs: float) -> Outcome:
    if tests > 80 and docs > 90:
        return Pass()
    return Fail(f"coverage is {tests}% for the tests, {docs}% for the documentation")
```
<!-- fmt:on -->

`by` may designate the producer itself, or any element above it, such as the conclusion
of the sub-argument it comes from. The integrator names the part of the argument they
mean, not the step inside it that happens to produce the value. A mapping also lets a
step take two values of one name under two parameter names, which the list form cannot.

### Diagnostics

| Code | When | Change |
|---|---|---|
| **JP009** `MissingProducer` | no bound step produces *n* | unchanged |
| **JP014** `ConsumedBeforeProduced` | *n* is produced, but no candidate supports the consumer (within `by`) | narrowed: a producer elsewhere in the model is no longer reported when a candidate exists |
| **JP025** `AmbiguousConsumption` | several candidates support the consumer (within `by`) | new, an error, reported on the consumer |
| **JP015**, **JP006** | `by` designates no element, or several by suffix | the binding rules, applied to `by` |
| **JP010** `DuplicateProducer` | — | **retired** |

A rule code never changes meaning (`Rule.code`). JP010's condition, two producers of one
name anywhere in the model, is no longer an error, so JP010 is retired rather than
redefined. Its number is never reused, and `docs/rules.md` lists it as retired, as the ADR
index lists retired ADR numbers. JP011, JP012 and JP013 keep their meaning, but are
computed over the resolution: a value is consumed when some consumption resolves to its
producer, not when its name appears in some `consumes`. For a model whose variable names
are distinct, every rule reports exactly what it reports today.

The resolution is built once, after binding, as a table of each step's parameters and
the producer each resolves to. The rules, the engine and the report all read it, as they
read the `BindingTable`.

### Values, the report, the diagram

- **`ValueStore`** holds a value under its producer's element and its variable name,
  rather than under its name alone. The engine passes each parameter the value of the
  producer it resolved to. "A variable is produced once" holds per producer. This amends
  the neutral consequence of [ADR-0009](0009-separate-registry-from-value-store.md): a
  name designates one value per consumer, not per run.
- **The report**, schema 2.1, adds an optional `inputs` to each element, mapping each
  parameter of its step to the variable it consumes and the element that produced it.
  `consumes` keeps listing the variable names, each once, and `produced` is already
  recorded per element. The events write an element as the report does
  ([ADR-0030](0030-a-run-streams-its-events.md)), so they carry `inputs` without a change
  of their own schema.
- **The diagram** draws one node per produced value (a producer and a name), rather than
  per name, and links each consumer to the node its parameter resolved to, using `inputs`.
  A consumption that did not resolve is drawn as today, in vermillion.

### The compiler

`PythonExporter` writes `consumes=[]` for the developer to fill in. The list form stays
valid, so the exporter needs no change. `Produced` is a new public name, and the authoring
guide documents it.

### Consequences

- Good, because libraries written against standalone models run together when the models
  are composed, with no edit and no coordination between their authors. The `assembled`
  scenario no longer needs `documented_release` to avoid a clash.
- Good, because a conflict is reported where it matters, on the one step that can see both
  values, and its author, the integrator, resolves it in their own library.
- Good, because the dataflow stays in the model and the libraries: no new source of values
  appears outside them.
- Good, because it is additive. Every library valid today resolves the same way, every
  report 2.0 field keeps its meaning, and models refused only by JP010 now run. This is a
  minor release.
- Bad, because a variable name no longer designates one value in a run. A tool that reads
  the report and indexes values by name alone, across elements, must use the producing
  element.
- Bad, because the rules move from an index of names to a resolution, which is harder to
  explain than "one name, one producer". The authoring guide must show the scoping with an
  assembled example.
- Bad, because a model that grows can make a consumption ambiguous: a new sub-argument
  producing the same name below an existing consumer raises JP025 there. This is the same
  trade-off as a suffix id in [ADR-0007](0007-binding-resolution.md), with the same fix,
  naming more precisely.
- Bad, because JP010 is the first retired rule code, and `docs/rules.md` needs a place
  for it.
- Neutral, because the second case of JP007, one step bound to several elements, was
  partly justified by such a step "producing the same variables twice". Values keyed by
  producer remove that reason, but the case stays an error: a step implements one element,
  and relaxing that is a decision of its own.

### Confirmation

- Unit tests of the resolution: one candidate, none (JP009, JP014), several (JP025), and
  `by` narrowing, designating nothing (JP015), or designating several elements (JP006).
- A property test over generated models whose variable names are distinct: the
  resolution agrees with today's name index, and no rule reports anything different.
- An e2e scenario with two libraries that each produce `coverage` for their own
  sub-argument, assembled, with the strategy `assemble` adds taking both through
  `Produced`. The `assembled` scenario's docstrings stop citing JP010.
- `docs/rules.md`, regenerated from `rules.py`, lists JP025 and JP010 as retired.
- The report schema test validates `inputs`, and `docs/report-schema.md` documents 2.1.
- `docs/design.md` shows the resolution table, as `tests/unit/test_design_doc.py`
  requires.

## Pros and Cons of the Options

### 1. Scope by the argument graph

- Good, because it follows a rule the runner already enforces (JP014): a value can only
  reach a step from below.
- Good, because a conflict exists only where one step sees two values, which is a real
  ambiguity and not an accident of names.
- Good, because the way to name a producer reuses the id resolution steps already use.
- Bad, because a variable is no longer a name, but a name and the element that produced
  it, wherever values are stored, reported or drawn.

### 2. Qualify a variable by the model its producer came from

- Good, because composition records each element's origin, which jPipe 4.0.0 writes to
  its JSON (#172), so a bare name could resolve within its origin model.
- Bad, because it depends on composition metadata rather than on the argument's structure:
  an element that unification merged from two sources, or a strategy `assemble` adds,
  belongs to no single origin.
- Bad, because it does not help when two libraries feed the same source model.

### 3. Qualify a variable by its library

- Good, because a library is exactly the unit an independent developer writes.
- Bad, because a library is not a concept of the model, and nothing in the argument shows
  which one a value comes from.
- Bad, because module names come from file names
  ([ADR-0020](0020-importing-step-libraries.md)), so two third-party `steps.py` already
  collide (JP021) before their variables do.

### 4. Rename at assembly time

- Good, because the libraries stay untouched, and the integrator decides.
- Bad, because the dataflow gets a source the model does not show: a run's values would
  depend on a file passed beside it, which is what
  [ADR-0008](0008-drop-external-variable-injection.md) removed.

### 5. One namespace, and a naming convention

- Good, because it costs nothing in the runner.
- Bad, because it needs exactly the coordination between authors that independent
  libraries lack, and a library already published cannot follow a convention adopted after
  it.

## More Information

- #187 (this decision); #183, on outputs and observed artifacts, which this decision does
  not settle; #172, the origins written by jPipe 4.0.0.
- [ADR-0007](0007-binding-resolution.md) (how `by` designates an element),
  [ADR-0009](0009-separate-registry-from-value-store.md) (amended: the value store's keys),
  [ADR-0010](0010-diagnostics-as-data-rules-as-objects.md) (codes and rules),
  [ADR-0011](0011-json-report-is-the-machine-readable-contract.md) (the report's versions),
  [ADR-0029](0029-the-runner-draws-the-dataflow.md) (the diagram).
- The names `Produced`, `by` and the report's `inputs` were accepted with this decision.
