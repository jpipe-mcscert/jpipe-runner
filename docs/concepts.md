# Concepts

The words the rest of the documentation uses, each defined once, here. The other pages
link to these definitions; [`tutorial.md`](tutorial.md) shows them at work on one example.

## The argument

### Justification

An argument written in jPipe: a conclusion, the reasoning that supports it, and the
evidence that reasoning rests on. Its source is a `.jd` file, which the jPipe compiler
compiles to JSON (`jpipe process -f JSON`), the only form the runner reads
([ADR-0001](adr/0001-consume-compiler-json.md)). Once the runner has loaded that JSON, the
justification is also called the **model**.

### Element

A node of a justification: a claim, a piece of reasoning, or a piece of evidence. Each has
an [id](#id-and-alias), a label and a [kind](#kind). An element **supports** the elements
above it, toward the conclusion; the elements below it are its **supporters**.

### Kind

What an element is, which decides how it is checked:

| Kind | Stands for | Its step |
|---|---|---|
| evidence | a fact about the world: a test report, a changelog | required; [observes](#artifact) files |
| strategy | the reasoning that turns what its supporters found into a claim | required |
| sub-conclusion | a claim established by the argument below it, which supports another | optional |
| conclusion | the claim the justification establishes | optional |

### Id and alias

How an element is named. The compiler qualifies each id by the justification's name: `e1`
in `justification release` is `release:e1`. [Composition](#composition) prefixes the ids
again, and an element merged from several keeps the ids it had in each source, as
**aliases**. A [step](#step) names its element by any of these, or by a unique tail of one
(`e1`): see [Binding](authoring.md#binding-how-an-id-designates-an-element).

### Composition

Building a justification from others: `refine` grafts a justification in place of an
evidence, `assemble` puts justifications under a new strategy and conclusion, and
unification merges elements that two justifications share. Composition prefixes ids, and
may turn an evidence or a conclusion into a sub-conclusion. The step libraries written for
the source justifications keep working on the composed one: see
[When the model is composed](authoring.md#when-the-model-is-composed).

## The step library

### Step

A Python function that checks one [element](#element), declared with the decorator of the
element's [kind](#kind): `@evidence`, `@strategy`, `@sub_conclusion` or `@conclusion`. The
decorator returns the function unchanged, so a step can be called directly, in a test.
[`authoring.md`](authoring.md) describes how to write one.

### Step library

A Python file of [steps](#step), given to the runner with `--library`. Several libraries
can run together, each imported as the module named after its file.

### Binding

Matching each [step](#step) to the [element](#element) its ids designate. A step **binds**
its element, and the element is **bound** to it. Binding is one to one: an element has at
most one step, and a step checks exactly one element. An evidence or a strategy must be
bound; a conclusion or a sub-conclusion left **unbound** takes its
[status](#status) from what supports it.

### Variable

A named value that flows up the argument: a step **produces** it, by returning it in a
`Pass`, and the steps above it **consume** it, as parameters of the same name. A variable
has one producer in a run, and the producer must support each consumer, so that the value
exists when the consumer runs.

### Artifact

A file an evidence **observes**: declared with `observes`, as a path or a glob, relative to
the [working directory](#working-directory), and passed to the step as a parameter. The
runner records each file it observed, with its SHA-256 and size, just before the step is
called. See [Observing artifacts](authoring.md#observing-artifacts).

### Outcome

What a step returns: `Pass(...)`, with the [variables](#variable) it produces,
`Fail(reason)`, or `Skip(reason)`. It becomes the [status](#status) of the step's element.
See [Returning an outcome](authoring.md#returning-an-outcome).

### Cross-check

A step declared as evidence and bound, after [composition](#composition), to a
sub-conclusion that is argued in full below it. It runs after that argument, and only if it
passed, as an independent check of the same claim; validation points it out with `JP008`.

## A run

### Working directory

The directory the runner runs in, and the root of the run: the paths an evidence observes,
and the paths a report shows, are relative to it.

### Validation

The check of the step libraries against the model, before any step runs: every element that
needs a step has one, ids bind one to one, every consumed variable is produced below its
consumer. Every problem is reported at once. [`rules.md`](rules.md) describes each check.

### Diagnostic

A problem the runner reports, with a code, `JPnnn`, that never changes meaning; a severity;
the element it is about, if any; a message; and, where there is something specific to do, a
fix. An **error** stops the run, or fails the element it is about; a **warning** changes
nothing else. A strict run (`--strict`) counts validation's warnings as errors, and only
those: a warning reported while the steps run, such as `JP024`, stays a warning.
[`rules.md`](rules.md) lists every code.

### Status

What a run concluded about one [element](#element): `pass`, `fail` or `skip`. A failure or a
skip **blocks** what the element supports: everything above it is skipped, its steps not
called. An element has no status when nothing ran.

### Verdict

What a run concluded about the whole justification: `pass` when every element passed,
`fail` when one failed, `skip` when none failed and one was skipped, `invalid` when nothing
could run, and `valid` when a dry run found nothing wrong. The command line's exit code
follows from it: see [Exit codes](cli.md#exit-codes).

### Report

What a run produces: the **text report**, for people at a terminal, and the **JSON
report**, the versioned contract for programs, described in
[`report-schema.md`](report-schema.md). A run has one however it ends, with its verdict
and its diagnostics, even when the model is refused or validation stops it; only a file
that cannot be read at all, such as a missing justification, leaves an error on stderr
and no report.
