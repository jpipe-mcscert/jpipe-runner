# Design

How jpipe-runner v4 is built, for contributors. This page describes the code as it is, not
the plan: update it in the commit that changes the design.

## Modules

```mermaid
flowchart LR
    json[/"justification JSON<br>(from the jPipe compiler)"/]
    schema[("justification.schema.json")]
    reportschema[("report.schema.json")]
    eventsschema[("events.schema.json")]

    json -.->|read by| loader
    loader -.->|validated against| schema
    loader --> model
    loader --> diagnostics
    model --> diagnostics
    outcomes --> diagnostics
    steps --> model
    steps --> observables
    steps --> outcomes
    values[values]
    records --> diagnostics
    binding --> model
    binding --> steps
    binding --> diagnostics
    dataflow --> binding
    dataflow --> diagnostics
    dataflow --> model
    dataflow --> steps
    validation --> binding
    validation --> dataflow
    validation --> model
    validation --> steps
    validation --> diagnostics
    rules --> validation
    rules --> binding
    rules --> dataflow
    rules --> model
    rules --> diagnostics
    artifacts --> steps
    artifacts --> observables
    artifacts --> diagnostics
    observables --> diagnostics
    artifacts --> records
    libraries --> diagnostics
    engine --> artifacts
    engine --> binding
    engine --> dataflow
    engine --> diagnostics
    engine --> model
    engine --> observables
    engine --> outcomes
    engine --> records
    engine --> rules
    engine --> steps
    engine --> validation
    engine --> values
    report --> observables
    report --> binding
    report --> dataflow
    report --> diagnostics
    report --> engine
    report --> libraries
    report --> model
    diagram --> dataflow
    diagram --> engine
    diagram --> model
    diagram --> report
    diagram -.->|piped to| dot[["Graphviz dot"]]
    json_report --> observables
    json_report --> diagnostics
    json_report --> records
    json_report --> report
    json_report -.->|validated against| reportschema
    events --> diagnostics
    events --> engine
    events --> json_report
    events --> model
    events --> report
    events --> validation
    events -.->|described by| eventsschema
    eventsschema -.->|refers to| reportschema
    text_report --> diagnostics
    text_report --> engine
    text_report --> model
    text_report --> observables
    text_report --> report
    impact --> observables
    impact --> json_report
    cli --> binding
    cli --> diagnostics
    cli --> diagram
    cli --> impact
    cli --> engine
    cli --> events
    cli --> json_report
    cli --> libraries
    cli --> loader
    cli --> model
    cli --> observables
    cli --> report
    cli --> steps
    cli --> text_report
    __main__ --> cli
```

A solid arrow is an import: the module at its tail uses the module at its head. A dotted
arrow is data.

| Module | Role |
|--------|------|
| [`cli`](../src/jpipe_runner/cli.py) | The command line, `jpipe-runner`: reads its options, runs a justification through the modules below, writes the report and the diagram, and returns an `ExitCode`. Entry point: `main(argv)`. |
| [`impact`](../src/jpipe_runner/impact.py) | What a change to a file reaches in an argument, from a JSON report: the evidence that observes changed files and what it supports, and the files a run observed that have changed since. Entry points: `affected(document, changed)`, `stale(document, root)`, `read(path)`. |
| [`__main__`](../src/jpipe_runner/__main__.py) | `python -m jpipe_runner`, which runs `cli.main` as the `jpipe-runner` script does. |
| [`loader`](../src/jpipe_runner/loader.py) | Reads the JSON the jPipe compiler emits, checks it against the schema, and builds a `Justification`. Entry points: `load(path)` and `loads(text)`. |
| [`model`](../src/jpipe_runner/model.py) | The justification model: elements, the relations between them, and the graph they form. |
| [`steps`](../src/jpipe_runner/steps.py) | The decorators that declare a step library's functions, `@evidence`, `@strategy`, `@sub_conclusion` and `@conclusion`, and the `StepRegistry` that collects them from the library's modules. |
| [`binding`](../src/jpipe_runner/binding.py) | Resolves the ids a step names to elements of the model, and binds steps to elements, one to one, in a `BindingTable`. |
| [`dataflow`](../src/jpipe_runner/dataflow.py) | Resolves each variable a bound step consumes among the step's supporters, in a `DataflowTable`: which step it comes from, or why none does. |
| [`validation`](../src/jpipe_runner/validation.py) | Checks a step library against its model before anything runs: `Rule`, one check; `RuleSet`, which runs rules over a `ValidationContext` and collects what they report in a `ValidationReport`. |
| [`rules`](../src/jpipe_runner/rules.py) | Every validation rule, one class each, and `RULES`, the rule set every run uses. [`rules.md`](rules.md) is generated from it. |
| [`engine`](../src/jpipe_runner/engine.py) | Runs a step library against its model: validates it, then calls the steps supporters first, and returns a `RunResult`, each element's `ElementResult` and the verdict, telling a `RunListener` as it goes. Entry point: `run(justification, registry)`. |
| [`libraries`](../src/jpipe_runner/libraries.py) | Imports a run's step libraries, each as a module named after its file, with the run's python path, and forgets them after the run. Entry point: `imported(libraries, python_path)`. |
| [`artifacts`](../src/jpipe_runner/artifacts.py) | Observes the artifacts of an evidence just before its step is called: what each was, what the step receives, and a `JP019` for each that could not be reached. |
| [`observables`](../src/jpipe_runner/observables.py) | What an evidence can observe: the `Observable` a step library derives, the built-in `File`, `JsonValue` and `Env`, the `Context` that anchors a path to the file that declares its step, and what a glob designates. |
| [`report`](../src/jpipe_runner/report.py) | The `RunReport` of a run, built for every way a run ends, even when nothing ran: each element of the model with its status, its step and what that step declares, observed and produced, then every diagnostic. Entry points: `RunReport.of(result)`, `RunReport.refused(error)`, `RunReport.not_imported(justification, error)`. |
| [`events`](../src/jpipe_runner/events.py) | The events of a run, written as it goes, one JSON object per line, for a program that shows the run while it runs: the `EventStream`, the engine's `RunListener`, which the command line tells when the run starts and ends. Each element and diagnostic is written as `json_report` writes it, and `events.schema.json` describes the events, referring to `report.schema.json` for those. |
| [`json_report`](../src/jpipe_runner/json_report.py) | Renders a `RunReport` as the JSON report, the machine-readable contract described by `report.schema.json` and [`report-schema.md`](report-schema.md). Entry points: `document(report)`, `dumps(report)`. |
| [`diagram`](../src/jpipe_runner/diagram.py) | Draws a run's dataflow: the justification in the jPipe compiler's notation, the files and variables its steps declare, and the run's statuses over it. Entry points: `source(justification, report)`, `write(path, justification, report)`. |
| [`text_report`](../src/jpipe_runner/text_report.py) | Renders a `RunReport` as text for a terminal, in the manner of Cucumber. Entry point: `render(report)`. |
| [`values`](../src/jpipe_runner/values.py) | The `ValueStore` of a run: the values its steps produced, each with the element that produced it. |
| [`records`](../src/jpipe_runner/records.py) | How a value the run saw is kept for its report: `snapshot`, a deep copy, or, for a value that cannot be copied, an `Uncopied`, its canonical `repr` and type taken then; and the canonical `repr` the JSON report writes a value that is not JSON with. |
| [`outcomes`](../src/jpipe_runner/outcomes.py) | What a step returns: `Pass`, carrying the values it produces, `Fail` or `Skip`. |
| [`diagnostics`](../src/jpipe_runner/diagnostics.py) | `Diagnostic`, what the runner reports about a model, a step library or a run, and `user_traceback`, an exception's traceback without the runner's frames. |
| [`framework`](../src/jpipe_runner/framework/__init__.py) | Not a module of v4: the v3 authoring API lived under this name, and importing it raises an `ImportError` that says what replaced it. |

The public API, what a step library imports, is the package itself: `from jpipe_runner
import evidence, strategy, sub_conclusion, conclusion, Outcome, Pass, Fail, Skip`. It is
loaded when first used, so that importing the package loads only the standard library.
What runs a justification, the command line, uses three entry points:
`loader.load(path)`, `libraries.imported(libraries, python_path)`, inside which
`engine.run(justification, registry)` runs. Whichever way the run ends, it builds a
`RunReport`, and renders it.

## Classes

```mermaid
---
config:
  class:
    hideEmptyMembersBox: true
---
classDiagram
    direction LR

    namespace cli {
        class ExitCode
    }

    namespace impact {
        class Impact
        class Change
        class ChangeKind
        class Unverified
        class Unchecked
        class InvalidReportError
    }

    namespace model {
        class Justification
        class Element
        class Relation
        class Kind
        class TemplateChain
        class Template
        class Placeholder
        class InvalidJustificationError
    }

    namespace steps {
        class Step
        class StepRegistry
        class Artifact
        class Input
        class Produced
    }

    namespace binding {
        class BindingTable
        class Binding
        class Resolver
        class AmbiguousIdError
    }

    namespace dataflow {
        class DataflowTable
        class Consumption
        class Received
    }

    namespace validation {
        class Rule
        class RuleSet
        class ValidationContext
        class ValidationReport
    }

    namespace rules {
        class UnboundElement
        class AmbiguousBinding
        class ConflictingBinding
        class RefinedElement
        class MissingProducer
        class UnconsumedOutput
        class EvidenceProducesNothing
        class StrategyIgnoresUpstreamOutput
        class ConsumedBeforeProduced
        class UnknownBindingTarget
        class IncompatibleKind
        class EvidenceObservesNothing
        class AmbiguousConsumption
        class DanglingTemplateChain
    }

    namespace engine {
        class RunResult
        class ElementResult
        class RunListener
        class Status
        class Verdict
    }

    namespace events {
        class EventStream
    }

    namespace libraries {
        class LibraryLoadError
    }

    namespace report {
        class RunReport
        class ElementReport
        class Summary
        class Trace
        class Frame
    }

    namespace artifacts {
        class Observed
    }

    namespace observables {
        class Observable
        class File
        class JsonValue
        class Env
        class Context
        class Sighting
        class Observation
        class Obstacle
    }

    namespace values {
        class ValueStore
        class ProducedValue
        class Unset
    }

    namespace records {
        class Uncopied
    }

    namespace outcomes {
        class Outcome
        class Pass
        class Fail
        class Skip
        class NotAnOutcomeError
    }

    namespace diagnostics {
        class Diagnostic
        class Severity
    }

    <<abstract>> Rule
    <<interface>> RunListener
    <<enumeration>> Kind
    <<enumeration>> Severity
    <<enumeration>> Unset
    <<enumeration>> Status
    <<enumeration>> Verdict
    <<enumeration>> ExitCode
    <<enumeration>> ChangeKind
    <<enumeration>> Unchecked

    Justification "1" *-- "*" Element : elements
    Justification "1" *-- "*" Relation : relations
    Relation ..> Element : source, target
    Element --> Kind : kind
    Justification "1" *-- "0..1" TemplateChain : template_chain
    TemplateChain "1" *-- "*" Template : templates
    Template "1" *-- "*" Placeholder : placeholders
    TemplateChain ..> Element : elements
    Template ..> Element : elements
    Placeholder ..> Element : id, supports
    Justification ..> InvalidJustificationError : raises
    Exception <|-- InvalidJustificationError
    InvalidJustificationError "1" o-- "1..*" Diagnostic : diagnostics
    Diagnostic --> Severity : severity
    Diagnostic ..> Element : element
    StepRegistry "1" o-- "*" Step : steps
    Step --> Kind : kind
    Step "1" *-- "*" Artifact : observes
    Step "1" *-- "*" Input : inputs
    Input ..> Produced : from
    Step ..> Outcome : returns
    BindingTable "1" *-- "*" Binding : bindings
    BindingTable ..> Resolver : uses
    Binding --> Element : element
    Binding --> Step : step
    Resolver ..> AmbiguousIdError : raises
    LookupError <|-- AmbiguousIdError
    RuleSet "1" o-- "*" Rule : rules
    RuleSet ..> ValidationContext : checks
    RuleSet ..> ValidationReport : returns
    ValidationContext --> Justification : justification
    ValidationContext --> StepRegistry : registry
    ValidationContext --> BindingTable : bindings
    ValidationContext --> DataflowTable : dataflow
    DataflowTable "1" *-- "*" Consumption : consumptions
    DataflowTable ..> Resolver : uses
    DataflowTable ..> Received : received
    Consumption --> Binding : consumer, candidates
    Consumption --> Input : input
    Rule ..> Diagnostic : reports
    ValidationReport "1" o-- "*" Diagnostic : diagnostics
    Rule <|-- UnboundElement
    Rule <|-- AmbiguousBinding
    Rule <|-- ConflictingBinding
    Rule <|-- RefinedElement
    Rule <|-- MissingProducer
    Rule <|-- UnconsumedOutput
    Rule <|-- EvidenceProducesNothing
    Rule <|-- StrategyIgnoresUpstreamOutput
    Rule <|-- ConsumedBeforeProduced
    Rule <|-- UnknownBindingTarget
    Rule <|-- IncompatibleKind
    Rule <|-- EvidenceObservesNothing
    Rule <|-- AmbiguousConsumption
    RunResult --> Justification : justification
    RunResult --> BindingTable : bindings
    RunResult --> DataflowTable : dataflow
    RunResult --> ValidationReport : validation
    RunResult "1" *-- "*" ElementResult : elements
    RunResult --> ValueStore : values
    RunResult ..> Verdict : verdict
    ElementResult --> Element : element
    ElementResult --> Status : status
    ElementResult --> Binding : binding
    ElementResult ..> Outcome : outcome
    ElementResult "1" *-- "*" Observation : observed
    ElementResult "1" o-- "*" Diagnostic : diagnostics
    ElementResult "1" *-- "*" Received : inputs
    RunListener ..> ElementResult : told of
    RunListener ..> ValidationReport : told of
    RunListener ..> RunResult : told of the planned
    RunListener <|.. EventStream
    EventStream ..> ElementReport : writes
    EventStream ..> RunReport : ends with
    Diagnostic ..> TracebackException : traceback
    RunReport "1" *-- "*" ElementReport : elements
    RunReport "1" o-- "*" Diagnostic : diagnostics
    RunReport ..> Verdict : verdict
    RunReport ..> Summary : summary
    RunReport ..> Trace : trace
    RunReport ..> RunResult : of
    ElementReport --> Kind : kind
    ElementReport --> Status : status
    ElementReport "1" *-- "*" Observation : artifacts
    ElementReport "1" *-- "*" Received : inputs
    Trace "1" *-- "*" Frame : frames
    Trace --> Trace : cause
    Exception <|-- LibraryLoadError
    LibraryLoadError "1" o-- "1..*" Diagnostic : diagnostics
    Observed "1" *-- "*" Observation : observations
    Observed "1" o-- "*" Diagnostic : diagnostics
    Artifact --> Observable : observable
    Observable <|-- File
    Observable <|-- JsonValue
    Observable <|-- Env
    Observable ..> Context : observed from
    Observable ..> Sighting : observe
    Sighting "1" *-- "*" Observation : observations
    Observation --> Obstacle : obstacle
    ValueStore "1" *-- "*" ProducedValue : values
    ProducedValue ..> Element : produced_by
    Outcome <|-- Pass
    Outcome <|-- Fail
    Outcome <|-- Skip
    TypeError <|-- NotAnOutcomeError
    NotAnOutcomeError "1" o-- "1" Diagnostic : diagnostic
    ExitCode ..> Verdict : from
    Change --> ChangeKind : kind
    Unverified --> Unchecked : why
    ValueError <|-- InvalidReportError
```

A `Justification` is a model loaded from the compiler: a name, its elements and its
relations. Each `Element` has a `Kind` (evidence, strategy, sub-conclusion, conclusion). A
`Relation` goes from the supporting element to the element it supports, so evidence are
the sources of the graph and the conclusion is its sink.

A justification that implements a template also has a `TemplateChain`: how the compiler
draws it, which jPipe writes since 4.0.0. It lists the elements drawn outside every
template, then each `Template` of the chain, the one implemented first, with the elements
drawn in it and its `Placeholder`s, the `@support`s that elements further down fill. The
run does not use it: the elements and relations are already the flattened argument. Only
the diagram reads it. So a chain that names an element the model does not have is not
kept: the diagram draws the argument flat, and validation warns (`JP026`).

**Elements are designated by id.** A `Relation` holds the ids of its two ends, and a
`Diagnostic` the id of the element it is about, not the `Element` objects; the dotted
arrows above are these references. An element also answers to its aliases, the ids of the
elements that composition merged into it, which binding resolution uses.

**The graph is hidden inside `Justification`.** It is a NetworkX `DiGraph`, but no
NetworkX type appears in the public API, and only `model` imports NetworkX. Callers ask the
model instead: `supporters(id)`, `supported(id)`, `upstream(id)` (every element that
supports it, directly or not) and `topological_order()`. Their results are deterministic,
ordered by model order, the order in which the model lists its elements: supporters,
supported and upstream elements are sorted by it, and the topological order breaks ties by
it.

**A model is immutable.** `Element`, `Relation` and `Diagnostic` are frozen dataclasses,
and the graph is frozen once built.

**A `Justification` is valid by construction.** A model that cannot be run is never
loaded. The loader rejects a document that is not JSON or does not match the schema
(`JP001`), and the `Justification` constructor rejects a duplicate element id (`JP002`) or
a relation naming an element that does not exist (`JP003`). An alias
counts as an id: one that another element also answers to is `JP002` too. Each of these
raises an `InvalidJustificationError` carrying every problem found, as diagnostics. So does
a cycle in the relations (`JP004`), reported once the rest is sound: the compiler never
emits one, and the steps of a cyclic argument would have no order to run in.

**A diagnostic's `code` is its contract.** The `message` is written for humans and may be
reworded. A `Severity.ERROR` found while loading or validating stops the run before any
step executes; one found while the steps run fails the element it is about, and the run
goes on. A `WARNING` is reported and changes nothing else.

**A step library is validated against its model before anything runs.** Each check is a
`Rule`, reified as a class: its `code`, `severity` and `summary` are class attributes, and
its docstring says what it checks, why, and how to fix what it reports, so that every rule
can be audited in one place. A `ValidationContext` holds what the rules read: the model,
the step registry, the `BindingTable` of one to the other, and the `DataflowTable` that
says where each value a bound step consumes comes from. A step that binds nothing never
runs, so the rules about data look only at bound steps. A `RuleSet` runs every rule, in code order, and collects
every diagnostic in a `ValidationReport`, which passes when none is an error. A strict run
reports warnings as errors. No rule can be disabled. What the model alone shows to be
unrunnable (`JP001` to `JP004`) is not a rule: the loader refuses it first.

**Every rule is in one module, `rules`, and the reference is generated from it.** Each
rule is a subclass of `Rule`. The rules about binding (`JP006`, `JP007`, `JP015`) report
what the `BindingTable` found, under their own code, and what the `DataflowTable` found of
the ids given as `by`. The rules about data read the `DataflowTable`. A step's
kind is compared with its element's: an evidence or a conclusion turned into a
sub-conclusion is what composition does, and is a warning (`JP008`); any other difference
is an error (`JP016`). [`rules.md`](rules.md), the reference
of every diagnostic code, is rendered from the rules' classes, and a test fails when the
committed page differs.

**A step library declares its functions with one decorator per kind.** `@evidence`,
`@strategy`, `@sub_conclusion` and `@conclusion` take the ids of the elements a function
implements, as positional arguments, and the variables it `consumes` and `produces`.
`consumes` is a list of variables, each passed to the parameter of its name, or a map
from each parameter to a variable or a `Produced`; the `Step` keeps it as `Input`s. Each
kind's decorator accepts only what the kind can do: evidence consumes nothing, and a
conclusion produces nothing. Only evidence `observes` artifacts: a mapping from parameter
name to an observable, or to a path, which stands for a `File`, kept on the `Step` as
`Artifact`s. A path names a file or a glob of files, never a directory. A decorator attaches a `Step`
to the function and returns the function unchanged, so a step is still a plain function.
A declaration that is wrong on its face is a `TypeError` when the library is imported: no
id, a variable or parameter name that is not a Python identifier, an absolute path or a
directory, or a parameter list that is not exactly the consumed variables, or for
evidence the observed artifacts (a parameter with a default, or `**kwargs`, is allowed).

**A consumed variable resolves among the consumer's supporters**
([ADR-0031](adr/0031-variables-resolve-among-supporters.md)). A step receives a value only
from a step that supports it, directly or not (`upstream`), because it runs only once its
supporters have passed. So the `DataflowTable` resolves each `Input` of a bound step, a
parameter and its variable, to its candidates: the bound steps that produce the variable
and support the consumer, narrowed, when the step consumes a `Produced(variable, by=id)`,
to the step of the element `by` designates if it produces the variable, and otherwise to
those below that element. Each input is a `Consumption`, with
every producer of its variable, those reachable from `by`, and the candidates. Exactly one
candidate is its producer. None is `JP009`, when nothing produces the variable, or `JP014`;
several is `JP025`, which a `by` resolves. Two steps may therefore produce one variable, as
libraries written apart for separate models do, and each consumer receives its own. A
nearer candidate never wins over a farther one. A producer's value is consumed when an
input draws on it (`users`): its candidates, or, when none supports the consumer, the
producers it names, so that `JP011` and `JP012` do not repeat a `JP014`.

**A step is bound to an element through the ids it names.** An id designates an element
if it is the element's id or one of its aliases, then if it is that prefixed with the
justification's name, then if it is a strictly shorter tail of one of those, cut at `:`.
An exact match always wins, and a tail of two elements' ids is ambiguous rather than
resolved to either. This is the rule the jPipe compiler uses to shorten the ids it writes
into a step library, so whatever it writes resolves. A `BindingTable` binds a registry's
steps to a model's elements one to one, and reports, without stopping, every id that
designates no element (`JP015`) or several (`JP006`), every element claimed by several
steps, and every step whose ids designate several elements (`JP007`). The elements of a
conflict are left unbound, and listed as `contested`, so that validation does not report
them again as unbound.

**Declaration and execution are kept apart, and neither is global.** What a step library
declares is a `StepRegistry`; what a run produces is a `ValueStore`. Both are built for a
run and dropped with it, and no module holds one, so two runs in one process share
nothing. `StepRegistry.from_modules` scans the namespaces of a library's modules for
steps, each listed once, in order, so a module that Python has cached is collected again
as it is. A `ValueStore` holds each `ProducedValue` under its variable and the id of the
element whose step produced it: what was produced, and by which element. An element
produces a variable once, and one that it has not produced reads as `UNSET`, which is not
`None`: `None` is a value a step can produce.

**A step reports its result by returning an `Outcome`.** `Pass` carries the values the
step produces, by variable name; `Fail` carries the reason the check does not hold; `Skip`
the reason the step declines to judge. Outcomes are frozen, and so are the values of a
`Pass`. A step that returns anything else, such as the `bool` a v3 step returned, is
reported with `JP017` by `as_outcome`, and the diagnostic's `fix` names the outcome to
return instead.

**What an evidence observes is an `Observable`**
([ADR-0028](adr/0028-observables-and-file-relative-paths.md)). It says how the report
names it (`describe`), what it is now (`observe`), and which files a change to reaches it
(`depends_on`). `File`, a file or a glob of files, is what a string in `observes` stands
for; `JsonValue` is a value in a JSON file, and `Env` an environment variable; a step
library derives `Observable` for anything else. `observe` returns a `Sighting`: the value
the step receives, and an `Observation` of each thing seen. A file's observation has its
path relative to the run's root, its SHA-256 and its size, read once, so the record is the
state the step is about to see; a value's has the value and its SHA-256, or says that it
is hidden. There is no observation without one or the other, and no sighting without an
observation: nothing a verdict rests on stays off the record. What could not be reached
has an `Obstacle` instead: a missing or unreadable
file, a directory or anything else that is not a regular file (a pipe, a device, which
could block the run), a glob that matches nothing, a variable that is not set.

**A path is relative to the file that declares the step**, not to the directory the runner
runs in, so a library observes the same files wherever it is run from. The decorator keeps
the directory of the function's file on the `Step`; an observable receives it in a
`Context`, with the run's root, and `Context.shown` turns a path relative to the first
into one relative to the second: the path the report shows, the one a changed file has.

**An evidence's artifacts are observed just before its step is called.**
`artifacts.observe` asks each observable of the step for its sighting, and returns what
was `Observed`: the observations, the arguments of the step, and a `JP019` diagnostic for
each obstacle. An observable is code of the step library: one that raises, or answers
anything but a sighting, is an obstacle too.

**What a glob designates is defined once**, beside what observes it. `files` lists the
regular files a glob matches under a root, and `matches` says whether it would match a
path, one segment at a time, without the file system and without a regular expression: a
run, `stale` and `affected` therefore agree on every glob, and a property test checks one
function against the other. A trailing `**` designates the files below it, on every
version of Python.

**A run's step libraries are imported for the run, and forgotten after it.** `imported`
is a context manager, and the steps run inside it. Each library is a module named after
its file (`steps.py` is `steps`, so that reports name a step `steps.function`),
registered in `sys.modules` before it runs, as an import would. A library whose file name
cannot be its module's name is refused before anything is imported (`JP021`): two
libraries with one name, a name another module already has, or a name that is not an
identifier. Every library is then imported, and each one that raises is reported
(`JP020`) at the line where it failed, with its traceback, which `user_traceback` trims
to the library's own frames. The `python_path` entries are first on `sys.path` while the
context lasts, so that a step importing a helper when it runs finds it, and on exit
`sys.path` is restored to what it was, even after an exception or a step that changed
it. The libraries leave `sys.modules` on exit, with the modules imported from the
`python_path` entries; third-party modules stay cached, since a C extension cannot be
imported twice in a process.

**A run validates, then calls the steps supporters first.** `run` builds the
`ValidationContext`, runs `RULES`, and executes only if no error was reported; otherwise
its `RunResult` has no element results and the verdict `INVALID`. Elements are taken in
`topological_order()`. An element a supporter of which did not pass is skipped, and its
`blocked_by` names the root causes: the elements upstream that failed, or were skipped,
on their own account, since every element in between was stopped by them. A failure and
a skip propagate alike, because what a step that did not pass would have produced does not
exist. An element whose supporters all passed has its step called, whatever its kind, so
a cross-check (`JP008`) runs after the argument below it; an unbound claim passes, and
one that nothing supports is skipped. A step is called with the values it consumes, each
read from the run's `ValueStore` as the producer its input resolved to produced it, and the
artifacts it observes, observed just before the call. Each `ElementResult` of a bound
element records what its step's parameters receive, as `Received`. Validation makes an
unset input impossible: a consumed variable resolves to one producer among the consumer's
supporters (`JP009`, `JP014`, `JP025`), and a `Pass` stores every value its step declares
or fails (`JP023`). The engine raises a `RuntimeError` rather than pass `UNSET`.

**What a step does wrong fails its element, and the run goes on.** An exception (`JP022`,
whose diagnostic carries the traceback, trimmed by `user_traceback`), a value that is not an outcome
(`JP017`), an unreachable artifact (`JP019`, and the step is not called) and a missing
declared value (`JP023`) fail the element, with the diagnostic on its `ElementResult`. An
undeclared value is dropped, with a warning (`JP024`): no step can consume it, so it
changes nothing. What a step produced is recorded on its `ElementResult` as a deep copy,
taken when it returned, so that a step that changes a value it consumes does not change
the record; a value that cannot be copied is recorded as its canonical `repr` and type,
taken then (`records.Uncopied`). `KeyboardInterrupt` stops the run. The verdict is `FAIL` if an element
failed, else `SKIP` if one was skipped, else `PASS`. The engine prints nothing: it logs
to the `jpipe_runner.engine` logger, and the report is built from the `RunResult`.

**Every way a run ends has a report, and renderers are pure functions of it** (the diagram,
of it and its model). A
`RunReport` is built from a `RunResult`, or, when nothing could run, from the
`InvalidJustificationError` of a refused model or the `LibraryLoadError` of libraries that
could not be imported. It is plain data: every element of the model, in topological order,
with its status (`None` when nothing ran), the step bound to it, what that step declares
(the artifacts it observes, the variables it consumes and produces, and where each input
comes from), and what the run
observed and produced; then every diagnostic, in the order found, and a `Summary` of both.
A diagnostic about an exception (`JP020`, `JP022`) carries its traceback, which the report
shows as a `Trace`: its frames' files relative to the run's root, and the same on every
Python version. The text renderer, `text_report.render`, lays a report out for a person, in
the manner of Cucumber: each element with a symbol for its status, its kind, its label and
its id, why it did not pass, then the diagnostics, the summary and the verdict. Its layout
is not a contract. Whether to colour it is the caller's decision (`use_colour`: a terminal,
unless `NO_COLOR` is set).

**The JSON report is the contract** ([ADR-0011](adr/0011-json-report-is-the-machine-readable-contract.md)).
`json_report.document` writes a report as the JSON document that `report.schema.json`,
shipped in the package, describes, versioned by `schema_version`. It is deterministic: no
time, relative paths, fields in a fixed order. A produced value is written as itself when
it is JSON, and as its `repr` and type otherwise, a `repr` made canonical: paths under the
root relative to it, sets sorted, no object addresses. [`report-schema.md`](report-schema.md)
documents it for readers.

**The diagram is the run's dataflow**
([ADR-0029](adr/0029-the-runner-draws-the-dataflow.md)). `diagram.source` writes the DOT
text of a justification in the compiler's notation: its quoted ids, its labels wrapped at
40 characters, its shapes and Okabe-Ito colours, nodes in model order and edges in the
order of the model's relations. A justification that implements templates is drawn as the
compiler draws it: each template a cluster nested in the one before it, each `@support` a
dotted placeholder linked to the element that fills it, and the template's supports drawn
from the placeholder. From what the report says the steps declare, it adds each
observed file and each variable as a node, linked to the elements that observe, produce
and consume it, and leaves out a support edge when a variable already links its two ends,
unless the template draws it from a placeholder; the edges through that variable then take
the colour of its producer's status, when it failed or was skipped.
A report's statuses are drawn over the elements in the same palette: a green border for a
pass, a vermillion fill for a failure, a dashed grey node for a skip. Each is also a symbol
beside the label, ✔, ✘ or ◌, in the label's colour, so that the diagram reads without its
colours. What an evidence observes is drawn in the shape its `Observable` says, and
marked ✔ once observed, or ⚠ with a vermillion border when it could not be; a variable has no mark,
and is vermillion when it lacks a producer or a consumer. **A status never moves the
diagram** ([ADR-0032](adr/0032-a-run-previews-its-diagram.md)): drawn with a report, every
element's and source's label has a cell of fixed size for its symbol, empty when there is
none, and a
failure keeps its kind's font, so the diagrams of a dry run and of any execution put every
node in the same place. `write` pipes the text to Graphviz's `dot`, only the `dot` format
being written without it, into a temporary file beside the path, then renames it: a
program reading the path never sees half a drawing. A diagram is drawn
from the model and the report together, and a report whose elements, or what each
supports, differ from the model's is refused.

**A dry run validates and calls no step**
([ADR-0024](adr/0024-dry-run-verdict-and-both-diagrams.md)). `run(..., dry_run=True)`
returns a `RunResult` without element results, as when validation stops a run, and its
verdict is `VALID` when validation reported no error. Its report lists every element with
its step and what that step declares, so its dataflow can be drawn.

**The command line composes the modules, and owns only what a process needs**
([ADR-0023](adr/0023-the-command-line.md)). `cli.main` parses the options, refuses
outputs it could not write before anything runs (a diagram whose suffix is not a format,
or that needs a `dot` that is not installed), then loads the model, imports the libraries
and runs the engine inside `imported`, with the working directory as the root. Between the
import and the engine, it refuses an output that names a file a bound step observes
([ADR-0035](adr/0035-an-output-never-overwrites-what-the-run-observes.md)): an events file
that holds something other than a run's events is opened without being emptied, and holds
its events until then. Each way
this ends gives a `RunReport`: `refused`, `not_imported` or `of`. It draws the diagram if
asked for, recording where on the report (`with_diagram`), writes the
JSON report to a file if asked, and prints the report on stdout: the text one, or the JSON
one. With `--events`, the `EventStream` is given a preview, which draws the diagram, in
SVG, in a temporary directory, from the `RunResult` the engine passes its listener once
validation passes and before the first step (`steps_starting`), as a dry run would draw
it, and the stream announces it (`diagram.drawn`); the command line deletes it once the run
has ended, however it ended. A preview that fails is logged, and changes nothing else.
Everything else goes to stderr, through the `jpipe_runner` logger, which `main`
configures for its duration only. A file that cannot be read or written is an `OSError`,
logged, and the exit code `IO`; the exit code of a run is otherwise `exit_code(verdict)`.
`python -m jpipe_runner` drops the working directory that Python puts on `sys.path`, so
that a library imports the same modules whichever way the runner is started.

**Impact and staleness read the JSON report, not the code**
([ADR-0025](adr/0025-impact-and-staleness.md)). The report is the contract (ADR-0011): it
says what each element supports, what its step declares it observes, and what the run
observed, with each file's SHA-256. `affected` takes the report of a dry run and the
changed files, and returns the evidence whose declared paths match one, then everything
above it (`above`), matching each file as a run would (`observables.matches`). `stale`
takes the report of an earlier run and compares each file it observed with the file now,
and lists what its globs designate now (`observables.files`). Each recorded file names
what it was `declared` as, so that neither a reader of the report nor the diagram matches
files to globs again. An environment variable is compared too, by the SHA-256 of its
value. `unverified` lists what the report cannot confirm: what it hides, and what is
neither a file nor a variable, which only its step library can observe again. While there
is any, `status` does not say that the report holds: it says that a new run is needed.
The command line's `impact` and `status` subcommands render what they return; `impact`
asks git for the changed files (`changed_since`) before importing anything, since an
import writes files of its own.
