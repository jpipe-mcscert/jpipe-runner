---
status: accepted
date: 2026-11-21
decision-makers: Sébastien Mosser
---

# ADR-0032: A run draws its diagram before its first step, and a status never moves it

## Context and Problem Statement

The IDE's Run panel colours a run's dataflow as the run goes, from the events `--events`
writes ([ADR-0030](0030-a-run-streams-its-events.md)). It needs a drawing of the dataflow
before the first step is called, and the runner gives it one only when the run ends:
`--diagram` is written once, with the run's statuses over it
([ADR-0029](0029-the-runner-draws-the-dataflow.md)). Without one, the panel would launch a
dry run with `--diagram` first, then the execution with `--events`. That imports the step
libraries twice, validates twice, delays the first step by a whole dry run, and lets the
two runs disagree if a file changes in between (#185).

A drawing taken before the run does not line up with the one taken after it either,
because a status changes the layout, not only the colours (#186). On the release example
(`tests/e2e/scenarios/release_example`), the dry run's diagram is 320×389 pt and the
execution's 360×412 pt, and every node moves, `mock/junit.xml` included, which no status
touches. Two things in `diagram.py` change an element's size:

- **The symbol cell.** An element with a status had an HTML-like label with a 20-point
  symbol before its text; an element without one had the compiler's plain label.
- **A failure's font.** A failure was drawn in Helvetica-Bold, other elements in the
  default Times. With `dot -Tplain`, the label "The test suite passes" is 2.12 in wide in
  Helvetica-Bold, 1.76 in in Times.

A border's width does not change a node's size: `penwidth` 1, 2 and 4 give the same node,
at the same place, in `dot -Tplain` (checked with Graphviz 16.1.1).

How should a run give a program that follows it a drawing before its first step, and how
can that drawing line up with the one the run ends with?

## Decision Drivers

- **One run.** The libraries are imported and validated once, and the drawing is of the
  run that follows it.
- **The events stay a preview** (ADR-0030): what the preview does never changes the
  verdict, the report or the exit code.
- **The drawings line up**: the drawing a program colours as the run goes, and the one the
  run ends with, put every node in the same place, whatever the statuses.
- **Nothing changes for whoever does not follow the run**: without `--events`, and in a
  dry run, the command writes what it wrote before.
- **`--diagram` holds the run's diagram**, and nothing else: no drawing without statuses
  can pass for it, and no step can observe one there.
- **The runner leaves behind no file that nobody named.**

## Considered Options

For where the drawing goes:

1. At the `--diagram` path, replaced when the run ends.
2. Beside it, under a name derived from it.
3. In an event, as SVG text.
4. In a temporary file, in SVG, which the runner deletes once the run has ended.

For how the events announce it:

1. A new event, `diagram.drawn`.
2. A field of `validation.ended`.

For the layout:

1. Leave it to the program that follows the run, which redraws the nodes it needs.
2. Reserve the symbol's cell in every label, and keep a failure's font.

## Decision Outcome

Chosen options: **in a temporary file the runner deletes once the run has ended,
announced by `diagram.drawn`, in a layout that reserves the symbol's cell**, because they
are the only ones under which one run gives a program a drawing to colour as the run goes,
that lines up with the run's diagram, while `--diagram` holds only that diagram and the
runner leaves nothing behind.

A first version of this record drew the preview at the `--diagram` path, replaced when the
run ended. Its review showed what that costs: a drawing without statuses at the path of
the run's diagram, which a step could observe while it ran, and which had to be withdrawn
when the final drawing failed, so as not to pass for it. A temporary file has neither
problem, and was chosen before the record shipped.

**When.** A run given `--events`, whose validation passes and which calls its steps, draws
its diagram once validation has ended and before the first element starts, as a dry run of
the same command would draw it: every element without a status. `--diagram` is not needed:
the program that follows the run gets its drawing without a diagram written in the user's
directory. A dry run writes no preview: its `--diagram` is already the dataflow without
statuses. Without `--events`, nothing changes, since nobody could learn that the drawing
was made.

**Where.** In SVG, which the IDE renders, as `diagram.svg` in a directory of its own that
the runner makes in the system's temporary directory, outside the project, where no step
observes it. The runner deletes it once the run has ended, after `run.ended` is written,
however the run ended. A program reads it when `diagram.drawn` arrives. A run that ends
quickly may delete it before a program gets to it: the drawing then has no use, and the
program shows the `--diagram` file `run.ended` names, if there is one. `--diagram` is drawn
once, at the end, as before. Every drawing is written to a temporary file beside its path,
then renamed to it, so that a program reading the path sees the previous drawing or the
new one, never half of one, and a drawing that fails leaves the previous one.

**The event.** `diagram.drawn`, with the drawing's absolute `path`, written after
`validation.ended` and before any element's event. It is part of events 1.0, which first
ships with 4.1.0, so no program has to handle a 1.0 stream without it.

**A preview.** A drawing that cannot be made before the first step, because Graphviz's
`dot` is not installed or for any other reason, is logged as a warning, and nothing else:
no `diagram.drawn`, and the run goes on.

**The layout.** Drawn with a report, every node's label is an HTML-like label, wrapped as
the compiler wraps it, beside a cell of fixed size for its symbol (`fixedsize="true"`),
empty when there is none: 28×32 pt for a status, at 20 points, and 22×22 pt for ⚠ on a
file or variable, at 14 points, wider and taller than the symbols need, so that no
symbol overflows on a platform whose fonts are larger. A failure keeps its kind's font:
the vermillion fill, the white text, the thicker border and ✘ already set it apart. This
amends ADR-0029, under which an element without a status kept the compiler's plain label,
and a failure was drawn in bold. Drawn without a report, the diagram is the argument
alone, in the compiler's notation, as before.

**In the code**, the engine tells its `RunListener` that the steps are about to run, with
the `RunResult` a dry run would have returned (`steps_starting`), once, before the first
element starts, and never in a dry run. `EventStream` takes a `preview` from the command
line, which draws the diagram from that result, and writes `diagram.drawn` if it drew it;
the command line deletes the drawing once the run has ended. This amends ADR-0030's listener, which was told of validation, of an element started and
of an element decided.

### Consequences

- Good, because the Run panel colours the drawing of the run it follows, from one command:
  the libraries are imported once, and the drawing cannot disagree with the run.
- Good, because `--diagram` holds only the run's diagram, written once, at the end, as in
  4.0.0: no step observes a preview there, and none can pass for the run's diagram.
- Good, because the preview and the final drawing put every node in the same place, as do
  the diagrams of a dry run and of any execution, and of two executions in which different
  elements fail: they can be compared by eye.
- Good, because a program that reads the diagram while the run writes it never sees half
  a drawing.
- Good, because a command without `--events`, and a dry run, write what they wrote before.
- Bad, because a run with `--events` calls `dot` once more, before its first step: on the
  release example, about 50 ms, most of a run that short.
- Bad, because a program must read the drawing while the run goes on: a run that ends
  before it does leaves it nothing to colour, only the `--diagram` file.
- Bad, because every node drawn with a report is a little wider, by the symbol's cell,
  and its label is HTML-like, even when it has no status: the diagram no longer reuses the
  compiler's label for an element without a status.
- Neutral, because the golden files change once: the diagram on the end-to-end page.

### Confirmation

- `tests/unit/test_diagram.py` draws the release shape under every combination of its
  evidence's outcomes, and with an unreachable file, and checks with `dot -Tplain` that
  every node is where the dry run puts it, and that a drawing that fails leaves the
  previous one and no temporary file.
- `tests/unit/test_events.py` runs every scenario with `--events`, and checks that
  `diagram.drawn` is written exactly when the steps run, after `validation.ended` and
  before any element's event, and that the drawing is gone once the run has ended. It
  checks that the preview is the dry run's diagram, in the temporary directory; that the
  `--diagram` file holds only the run's diagram; that a dry run, and a run without
  `--events`, draw no preview; that a preview that cannot be drawn, Graphviz missing
  included, is logged and changes nothing else; and that the preview is deleted however
  the run ends.
- `tests/unit/test_engine.py` checks that the listener is told of the steps starting,
  once, with a result that reports as a dry run of the same library does.
- `tests/unit/test_events_doc.py` checks that [`events.md`](../events.md) documents the
  event.

## Pros and Cons of the Options

### Where the drawing goes

#### 1. At the `--diagram` path

- Good, because there is one file, which the user named, and nothing to clean up.
- Bad, because a drawing without statuses sits at the path of the run's diagram while the
  steps run: a step that observes that path receives it, and a final drawing that fails
  leaves it to pass for the run's diagram, unless it is withdrawn.
- Bad, because it needs `--diagram`: the program that follows the run writes a diagram in
  the user's directory to get its drawing.

#### 2. Beside it

- Good, because the final drawing is never replaced.
- Bad, because the runner writes a file nobody named, which a program then has to find
  and clean up.

#### 3. In an event

- Good, because no file is written.
- Bad, because an event line runs to tens of kilobytes, and only SVG fits in it.

#### 4. In a temporary file, deleted once the run has ended

- Good, because `--diagram` keeps its meaning, the run's diagram, and the drawing is
  outside the project, where no step observes it.
- Good, because it needs no `--diagram`, and leaves nothing behind.
- Bad, because the drawing is gone once the run has ended: a program that reads it too
  late has only the `--diagram` file.

### How the events announce it

#### 1. A new event, `diagram.drawn`

- Good, because it says what happened when it happened, and a program that does not know
  it ignores it.
- Neutral, because one more event is documented and validated.

#### 2. A field of `validation.ended`

- Good, because there is one event fewer.
- Bad, because the field would be null in every stream without a preview, and
  `validation.ended` would say something that is not about validation.

### The layout

#### 1. Left to the program that follows the run

- Good, because the runner's diagram does not change.
- Bad, because the drawing jumps when the run ends, the panel has nowhere to put a symbol
  without covering the label, and two of the runner's diagrams still cannot be compared.

#### 2. A reserved cell, and a failure's font kept

- Good, because a status changes colours and symbols, never a node's size.
- Bad, because every node is a little wider, by its cell.

## More Information

- #185 (the preview) and #186 (the layout), both for the IDE's Run panel.
- [ADR-0029](0029-the-runner-draws-the-dataflow.md), the diagram, and
  [ADR-0030](0030-a-run-streams-its-events.md), the events, both amended by this record;
  [ADR-0024](0024-dry-run-verdict-and-both-diagrams.md), the dry run's verdict.
- [`events.md`](../events.md#diagramdrawn) and [`cli.md`](../cli.md) describe the
  behaviour.
