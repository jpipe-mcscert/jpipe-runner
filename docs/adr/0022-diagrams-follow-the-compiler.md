---
status: accepted
date: 2026-10-09
decision-makers: Sébastien Mosser
---

# ADR-0022: Diagrams follow the compiler's, with a status overlay and a dataflow view

## Context and Problem Statement

v3 drew the justification after a run with the `graphviz` Python package, in a style
copied from the jPipe compiler at the time: a grey rounded rectangle for the conclusion,
a blue-bordered rectangle for a sub-conclusion, an amber hexagon for a strategy, a blue
note for evidence. Over it, it drew a failed element filled red with white bold text, a
skipped one filled `#cccccc` with white text, and coloured each edge by the status of its
source. #123 asked to keep that behaviour.

Since then, the compiler (jPipe 2.5.0, `DotExporter`) has drawn the same model
differently. It keeps each element's id, quoted, as its DOT id and its SVG `id`, where v3
rewrote `:` as `_` to get around the way the `graphviz` package splits `node:port`. It
wraps labels at 40 characters. And it chose its colours from the Okabe-Ito palette, so
that readers with any of the common colour-vision deficiencies can tell them apart. v3's
overlay is not in that palette, and its white text on light grey is hard to read for
anyone. A user who draws a model with `jpipe process -f SVG`, then runs it with the runner,
sees two drawings of one argument.

Two more needs appeared with M3 and M4. Evidence declares the files it observes, and every
step the variables it consumes and produces (ADR-0018, ADR-0019): the argument has a
dataflow that validation checks (JP009 to JP014) and that no drawing shows. And #145 asked
for the files an evidence observed to be drawable, as nodes behind a flag.

How should the runner draw a justification and a run?

## Decision Drivers

- **One argument, one drawing**: what the compiler draws and what the runner draws should
  be the same picture, the runner adding only what the run concluded.
- **Readable by everyone**: colours from one palette that colour-blind readers can tell
  apart, and never colour alone.
- **The dataflow is part of the argument**: a reader should see which files feed which
  evidence, and which values flow to which strategy, before and after a run.
- **Only Graphviz** should be required to draw, and nothing to test the drawing.

## Considered Options

1. Keep v3's drawing (#123 as first written).
2. Follow the compiler's drawing, draw the run's statuses over it in the compiler's
   palette, and add a dataflow view.
3. Draw with Mermaid instead of Graphviz.

## Decision Outcome

Chosen option: **2, follow the compiler**, because it is the only one that gives one
drawing of an argument, whichever tool drew it.

- **A diagram is drawn from the model and a report of it.** The compiler's drawing follows
  the order of the model's elements and relations, which the report does not keep, so the
  model is drawn, and the report's statuses over it. A report whose elements, or what each
  supports, differ from the model's is refused.
- **The drawing of a model is the compiler's**, byte for byte: its ids, quoted, with
  `id=`; its labels, wrapped at 40 characters and escaped as it escapes them; its
  shapes and colours; the model's name as the graph's label. A run in which nothing ran
  is drawn the same way. v3's `:` → `_` rewriting is gone, and with it the ids of two
  elements that rewrote to the same one.
- **A run's statuses are drawn over it, in the Okabe-Ito palette**: a passed element keeps
  the compiler's node with a green (`#009E73`) border; a failed one is filled vermillion
  (`#D55E00`) with white bold text; a skipped one is filled light grey with a dashed grey
  border, thicker when it skipped on its own account, a root cause (ADR-0021). An edge
  takes the colour of its source's status, dashed when the source was skipped. A status is
  never colour alone: a failure is bold, a skip dashed, and in SVG each node's tooltip
  gives its status and reason.
- **The dataflow view** draws, on the same argument, each file or glob an evidence
  observes, as a folder linked to it by a dotted `observes` edge, and each variable as an
  ellipse linked to the steps that produce and consume it by dashed blue edges. It is drawn
  from what the steps declare, which the report carries (ADR-0011), so it can be drawn for
  a run that validation stopped: a variable with no producer or no consumer, or with
  several producers, is vermillion, and so is a file that could not be reached. A variable
  that was not produced in the run is dashed grey. This view replaces #145's "artifacts as
  nodes behind a flag".
- **Rendering pipes the DOT text to `dot`**, as the compiler does. The `graphviz` Python
  package, which only wrapped that call, is no longer a dependency. The `dot` format is
  the DOT text itself, written without Graphviz; v3 ran it through `dot -Tdot`, which added
  layout coordinates.
- **Where the diagram is written is the command line's** (#124). `write` takes a path,
  creates its directory, and takes the format from its suffix unless told otherwise;
  `default_name` gives `<justification>.<format>`, and `<justification>-dataflow.<format>`
  for the dataflow view.

### Consequences

- Good, because the compiler's drawing and the runner's are one picture: a reader learns
  one notation.
- Good, because statuses read without colour, and the colours are distinguishable with a
  colour-vision deficiency.
- Good, because the dataflow that validation checks can be seen, even when validation
  stopped the run.
- Good, because one dependency is gone, and the DOT text can be tested as text, without
  Graphviz.
- Bad, because the drawing must follow the compiler's: a change to `DotExporter` is a
  change to make here. A test compares the runner's drawing of four models with the
  compiler's output, kept verbatim next to them.
- Bad, because v3 users see different colours after a run.

### Confirmation

- `tests/unit/test_diagram.py` checks that the drawing of the four scenarios written in
  jPipe, run or not, is the compiler's `justification.dot`; checks the overlay, the
  dataflow view and the formats; and, where `dot` is installed (CI), renders every format
  and reads the SVG's ids and colours back.

## Pros and Cons of the Options

### 1. v3's drawing

- Good, because v3 users know it.
- Bad, because it differs from the compiler's drawing of the same model.
- Bad, because its overlay is not colour-blind safe, and its skipped nodes are hard to
  read.
- Bad, because it rewrites ids, which can make two elements one.

### 2. The compiler's drawing, with an overlay and a dataflow view

- Good, because it is one notation across jPipe's tools.
- Bad, because it is coupled to the compiler's exporter.

### 3. Mermaid

- Good, because GitHub renders it inline, in a pull-request comment.
- Bad, because the compiler draws with Graphviz: two notations again.
- Bad, because it has no shapes for a note or a folder, and lays large graphs out poorly.

## More Information

- #123 (the diagram), #145 (artifacts, the dataflow view), #124 (where it is written).
- [ADR-0011](0011-json-report-is-the-machine-readable-contract.md), the report the
  diagram is drawn from; [ADR-0019](0019-evidence-observes-files.md), observed files;
  [ADR-0021](0021-execution-semantics.md), statuses and root causes.
- The compiler's `DotExporter`, `DotLabel` and `DotNodeStyle`, in `jpipe-model`
  (jPipe 2.5.0).
