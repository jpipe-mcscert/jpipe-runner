---
status: accepted
date: 2026-11-21
decision-makers: Sébastien Mosser
---

# ADR-0034: A failure's path through a variable takes its status

## Context and Problem Statement

The diagram leaves out a support edge when a variable already links its two ends: the
supporter produces a variable that the element it supports consumes, and the path through
the variable shows the support and the data that flows along it
([ADR-0029](0029-the-runner-draws-the-dataflow.md)). A support edge takes the status of the
element it comes from: vermillion and thicker from a failure, dashed and grey from a skip.
The path through a variable was always drawn as data, dashed and blue, whatever its
producer's status.

So when evidence `e` fails and produces `v`, which strategy `s` consumes, nothing on the
path from `e` to `s` shows that the failure travelled along it. The nodes do: `e` is ✘ and
vermillion, `s` is ◌ and grey. ADR-0029 recorded this as neutral. Should the path show the
status, now that a reader follows a failure through the diagram (#176)?

## Decision Drivers

- **A reader follows a failure** from the evidence that failed to what it stopped.
- **A support is drawn once** (ADR-0029): no edge that duplicates a variable's path.
- **A status never moves the diagram** ([ADR-0032](0032-a-run-previews-its-diagram.md)): the
  drawing of a dry run, and of runs with other statuses, put every node in the same place.

## Considered Options

1. Keep the path as data: the nodes carry every status, with a colour and a symbol.
2. Draw the status on the path: the `produces` edge from an element that failed or was
   skipped, and the `consumes` edges from the value it produced, take that status's colour.
3. Draw the support edge again when its source did not pass, beside the variable's path.

## Decision Outcome

Chosen option: **2, the status on the path**, because it shows the failure where it goes
without adding an edge.

An edge through a value takes the status of the element that produced it, when that element
failed (vermillion) or was skipped (grey): the `produces` edge from it, and every `consumes`
edge from the value. It stays dashed, as every data edge is, and no thicker: a support
edge from a failure is thicker, but a status changes no width here. An edge from an element
that passed, or from one with no status yet, as in a dry run, stays blue: it is data. This
amends ADR-0029.

### Consequences

- Good, because the path from a failure to what it stopped reads in one colour.
- Good, because no edge is added: the support is still drawn once.
- Neutral, because an edge through a value now says two things, the data and its producer's
  status, as a support edge says the support and its source's status.
- Bad, because the failure's path is told by colour alone; its two ends carry their symbols,
  ✘ and ◌.

### Confirmation

`test_diagram.py` checks the colour of the path from an element that failed, was skipped and
passed, and that a dry run draws every data edge blue. `test_a_status_never_moves_the_diagram`
still holds.

## Pros and Cons of the Options

### 1. Keep the path as data

- Good, because an edge means one thing.
- Bad, because nothing between `e` and `s` says the failure went that way.

### 2. The status on the path

- Good, because the failure is shown along the path, and no edge is added.
- Bad, because colour alone tells it; a thicker line would move the drawing.

### 3. The support edge again

- Good, because the failure travels along a support edge, as it does when no variable
  links the two.
- Bad, because it brings back the duplicate edge ADR-0029 removed, on every failing run.
- Bad, because an edge drawn only on some runs changes the layout, against ADR-0032.

## More Information

Issue #176, raised by the review of #175.
