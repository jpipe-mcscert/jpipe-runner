---
status: accepted
date: 2026-11-17
decision-makers: Sébastien Mosser
---

# ADR-0029: The runner draws one diagram, the dataflow

## Context and Problem Statement

ADR-0022 gave the runner two views of a run. `--diagram` drew the argument as the jPipe
compiler draws it (`jpipe process -f SVG`), byte for byte, with each element's status over
it. `--dataflow` drew the same argument, and added the files each evidence observes and the
variables the steps produce and consume.

The first view is the compiler's drawing in other colours. A reader holding both pictures
of one argument has to work out that they differ only in colour, and which tool drew which.
It also could not keep its promise: for a justification that `implements` a template, the
compiler draws the template as a cluster, with placeholders for its `@support`s, which the
JSON the runner reads did not describe until jPipe 4.0.0 (#171, jpipe-compiler#199). What
the runner adds to an argument is its dataflow: what each evidence observes, which values
flow from which step to which, and what validation found wrong with it (JP009 to JP014).
That is the view only the runner can draw.

The dataflow view also drew every support twice when data flows along it: the support edge
from evidence to strategy, and the path from the evidence through the variable it produces
to the strategy that consumes it.

How many diagrams should the runner draw, and how?

## Decision Drivers

- **The runner shows what only the runner knows**: the argument itself is the compiler's
  to draw.
- **One picture of a run**, so that a reader never compares two.
- **No edge says what another already says.**
- **The report is a versioned contract** (ADR-0011): a field that goes is a new major
  version, and saved reports must not stop working for no reason.

## Considered Options

1. Keep both views (ADR-0022).
2. One diagram, the dataflow, drawn by `--diagram`; `--dataflow` goes.
3. One diagram, the dataflow, drawn by `--dataflow`; `--diagram` goes.

## Decision Outcome

Chosen option: **2, one diagram drawn by `--diagram`**, because it keeps the name every
user and the GitHub Action already pass, and the one view the runner exists to draw.

- **`--diagram PATH` draws the dataflow**: the justification, with each file or glob an
  evidence observes and each variable a step produces or consumes, and the run's statuses
  over its elements, as ADR-0022 drew the dataflow view. `--dataflow` is removed: passing it
  is a usage error.
- **A support edge is left out when a variable already links its two ends**: when the
  supporter produces a variable the element it supports consumes. The path through the
  variable shows the support, and what flows along it. A support that no variable links,
  such as a strategy's support of a conclusion, is drawn as before, in the colour of its
  source's status.
- **The elements keep the compiler's notation**: its shapes, its Okabe-Ito colours, its
  quoted ids and its labels wrapped at 40 characters, so that a reader who knows the
  compiler's drawings recognizes them. The diagram no longer claims to be the compiler's
  drawing: the tests that compared it with the compiler's DOT for every scenario, and the
  compiler output they kept, are gone.
- **Each status is a symbol as well as a colour**: ✔ for a pass, ✘ for a failure, ◌ for a
  skip, beside the label, in the label's colour. What an evidence observes is marked ✔
  once observed, and ⚠ in vermillion when it could not be. A variable has no symbol: a
  problem with it, no producer or no consumer, is known from the declarations, and it is
  drawn in vermillion. A support edge from a failure is thicker, as one from a skip is dashed. The
  Okabe-Ito palette tells its colours apart for most colour vision deficiencies, but a pass
  was a green border alone, and a printed or greyscale diagram loses the colours: the
  symbols carry the status without them. The symbol takes the label's colour, black or
  white on a failure, because the status colours contrast too little with the fills of the
  compiler's notation (green on an evidence's blue is 2:1). The label of an element with a
  status is an HTML-like label, a symbol beside the text, wrapped where the compiler wraps
  it; an element without a status keeps the compiler's label.
- **What an evidence observes is drawn in the shape of its kind**, which its `Observable`
  says (`shape`): a file a `tab`, a glob a `folder`, a value in a JSON file a `component`,
  an environment variable a `house`, and an observable of a step library a `box3d`
  unless it says otherwise. A step library's observable chooses among shapes that mean
  nothing else in the diagram, and another is refused when the library is imported. The
  diagram drew every source as a folder, so an environment variable looked like files.
- **The templates a justification implements are drawn as the compiler draws them**, from
  the template chain jPipe 4.0.0 writes to the JSON (`implements`): each template a cluster
  nested in the one before it, each `@support` a dotted placeholder linked to the element
  that fills it, and the template's supports drawn from the placeholders. Those supports
  are drawn even when a variable links their ends: they are the template's structure, and
  the variable, drawn from the element that fills the placeholder, shows the data. A
  placeholder has no step, so no status; a support drawn from it takes the colour of the
  element that fills it. A justification compiled by an earlier jPipe has no chain, and is
  drawn flat. So is one whose chain names an element the model does not have: the run
  does not read the chain, so a chain that names an element the model does not have is set
  aside, with a warning (`JP026`), rather than refusing an argument that runs (#177).
- **The report's `dataflow` field is removed, and the report becomes 2.0.** `diagram` is the
  path of the one diagram. Schema 1.1 was never released: 2.0 also carries what 1.1 added.
- **`impact` and `status` read reports of version 1.x as well as 2.x.** The field 2.0
  removed is one they never read, and a report saved by an earlier runner, such as the
  baseline a pipeline compares against, keeps working.

This supersedes [ADR-0022](0022-diagrams-follow-the-compiler.md), and amends
[ADR-0011](0011-json-report-is-the-machine-readable-contract.md) (the report's version),
[ADR-0023](0023-the-command-line.md) (the options) and
[ADR-0024](0024-dry-run-verdict-and-both-diagrams.md) (the `dataflow` field).
`--dry-run --diagram PATH` still draws the dataflow the libraries declare, without calling
a step.

### Consequences

- Good, because a run has one picture, and it shows what the runner checks.
- Good, because the diagram no longer follows the compiler's exporter for every model:
  only a template chain is drawn as the compiler lays it out, from what the JSON says of it.
- Good, because a support with data flowing along it is drawn once.
- Good, because a reader sees which elements a justification inherits from its templates,
  and which of its own fill their `@support`s.
- Bad, because a user of `--dataflow` must pass `--diagram` instead, and a reader of the
  report's `dataflow` must read `diagram`, and accept version 2.0. jpipe-vscode's Run panel
  passes `--dataflow` and reads `dataflow`; the GitHub Action passes `--dataflow` when its
  `dataflow` input is true.
- Bad, because the drawing of templates depends on the compiler's `implements` export: a
  change to it reaches the runner.
- Bad, because `--diagram` users see more than the argument: the files and variables too.
  A reader who wants the argument alone has the compiler's drawing.
- Neutral, because a support edge carried its source's status in its colour; the element
  still carries it.
- Neutral, because the symbols need a font that has them where `dot` renders a PNG or a
  PDF; an SVG leaves them to the browser.
- Neutral, because a template's support is drawn even when a variable links its ends, so a
  templated diagram can show a support twice, once as the template's and once as data.

### Confirmation

- `tests/unit/test_diagram.py` checks the notation, the statuses, the files and variables,
  which supports are drawn and which are left out, and, where `dot` is installed, the SVG.
  It draws a chain of two templates exactly as `jpipe process -f DOT` does (jPipe 4.0.0),
  and checks a run of the `templated` scenario: its placeholders, and the template's
  support drawn from one even though a variable links its ends.
- `tests/unit/test_cli.py` checks that `--diagram` draws the dataflow and records it, and
  that `--dataflow` is a usage error.
- `tests/unit/test_impact.py` checks that a report of version 1.1, with its `dataflow`
  field, is read.
- `tests/unit/test_end_to_end_doc.py` checks that the diagram in
  [`end-to-end.md`](../end-to-end.md) is the one the run draws.

## Pros and Cons of the Options

### 1. Both views

- Good, because nothing changes for users.
- Bad, because a run has two pictures, one of which is the compiler's in other colours.
- Bad, because the compiler's drawing of a template cannot be followed from its JSON.

### 2. One diagram, drawn by `--diagram`

- Good, because the option every user and the Action already pass keeps working.
- Bad, because what `--diagram` draws changes, and `--dataflow` goes.

### 3. One diagram, drawn by `--dataflow`

- Good, because the option says what it draws.
- Bad, because the option most users pass, `--diagram`, goes, and so does the Action's
  default.

## More Information

- #171 (diagrams of a justification that implements a template), jpipe-compiler#199 (the
  template chain in the JSON export, jPipe 4.0.0).
- [ADR-0021](0021-execution-semantics.md), statuses and root causes;
  [ADR-0025](0025-impact-and-staleness.md), `impact` and `status`.
