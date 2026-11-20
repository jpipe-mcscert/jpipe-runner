---
status: accepted
date: 2026-11-20
decision-makers: Sébastien Mosser
---

# ADR-0030: A run streams its events to a file, one JSON object per line

## Context and Problem Statement

The VS Code extension's Run panel (jpipe-vscode#107) draws a run's dataflow beside the
editor. It reads the JSON report written with `--report`
([ADR-0011](0011-json-report-is-the-machine-readable-contract.md)), which arrives whole
when the run ends. Until then, the panel can only show that a run is under way, however
long the steps take, and steps are where a run spends its time: they run test suites,
scanners and builds. To colour each element as the run goes, the IDE needs to know when
validation ends, when a step is about to be called, and when each element is decided
(#169).

Three facts constrain how the runner tells it. stdout carries the report and nothing else
([ADR-0023](0023-the-command-line.md)), and what the steps print goes to stderr, so
neither can carry anything a program parses. The extension runs the runner as a VS Code
task, whose terminal shows what the runner writes, so the extension does not hold the
runner's pipes. And the engine calls one step at a time today, but #174 proposes to call
independent steps together: whatever order the events promise must still hold then.

What should the runner emit while it runs, where, and with what promises?

## Decision Drivers

- The report stays the authority: the events preview it, and never contradict it.
- One piece of code reads an element in the report and in an event.
- It works on every platform the runner ships for, from a VS Code task.
- What a consumer may count on still holds when steps run concurrently (#174).
- A preview that cannot be written never changes the verdict.
- The engine knows nothing of files or JSON: it prints nothing, and what renders a run
  reads what it returns.

## Considered Options

For where the events go:

1. stdout.
2. A pipe or a file descriptor the caller opens, such as file descriptor 3.
3. A file the runner writes, `--events PATH`, one JSON object per line.

For the contract:

1. Part of the report's schema and version (ADR-0011).
2. A schema and a version of their own, which refer to the report's for an element and a
   diagnostic.

For when a skipped element is decided:

1. As soon as one element it depends on fails.
2. Once every element that supports it is decided.

## Decision Outcome

Chosen options: **a file, `--events PATH`, in JSON Lines**, **a schema of its own that
refers to the report's**, and **an element is decided once every element that supports it
is**, because they are the only ones that work from a VS Code task on every platform,
version the events without making every change to them a change of the report, and keep
every event in agreement with the report.

**The events.** `run.started` gives the versions and every element's id, once the model is
read or refused; `validation.ended`, what validation reported; `element.started`, that an
element's step is about to be called; `element.decided`, the element as the report will
write it, with its diagnostics; `run.ended`, the verdict, the exit code, the summary, and
where the report and the diagram were written. Each event has `seq`, its place in the file,
and `elapsed_ms`, the milliseconds since the file was opened. The report holds no time, so
that it is deterministic; the events do, since a program that shows a run as it goes has
a use for how long each step took, and they are a preview, not a record.

**The order is causal**, and nothing more: `run.started` first, `run.ended` last,
validation before any element, an element decided after every element that supports it,
and after it started. Two elements' events may come in any order, and interleave. A
consumer that relies on this needs no change when #174 calls steps together.

**A skip is decided when the engine reaches it**, once every element that supports it is
decided. `blocked_by` names every root cause among them
([ADR-0021](0021-execution-semantics.md)), so an element skipped as soon as one cause
failed, while another supporter still runs, would name too few causes, and contradict the
report.

**The file** is emptied when the run starts, and each line is written whole and flushed as
its event happens. A file that cannot be opened stops the command before anything runs,
with exit code 4. An event that cannot be written once the run has started is logged, the
stream stops, the run goes on to its report, and the command exits with code 4.

**In the code**, the engine tells a `RunListener` as it goes, from the thread that runs it:
validation ended, an element started, an element decided. `events.EventStream` is that
listener, and writes the events; the command line tells it when the run starts and ends.
The listener is not part of the public API (`from jpipe_runner import …`): `--events` is
the contract.

### Consequences

- Good, because the Run panel can colour each element as soon as it is decided, and say
  which step is running.
- Good, because an element in an event is the report's, encoded by the same function: a
  consumer parses both with one piece of code, and a test checks that the events of every
  scenario are the elements and the diagnostics of its report.
- Good, because a stream without `run.ended` tells a consumer that the run was stopped.
- Good, because the order promised holds when steps run concurrently (#174).
- Bad, because the events are not deterministic, unlike the report: they cannot be
  compared byte for byte, and a test masks `elapsed_ms`.
- Bad, because a consumer follows a file rather than reading a pipe, and has to read whole
  lines only, since the last one may still be in the middle of being written.
- Bad, because an element is written whole in each event that decides it, which repeats
  what the report says once the run ends.

### Confirmation

- `tests/unit/test_events.py` runs every scenario with `--events` and `--report`, and
  checks each event against `events.schema.json`, then that the events preview the report
  (its elements, its diagnostics, its verdict and its summary), and the order promised.
- `tests/unit/test_execution_properties.py` checks, over generated models, that the
  elements decided are the report's, each after its supporters, and that an element starts
  exactly when its step is called.
- `tests/unit/test_events_doc.py` checks that [`events.md`](../events.md) quotes the events
  a run writes, and documents every field of every event.

## Pros and Cons of the Options

### Where the events go

#### 1. stdout

- Good, because no file is left behind.
- Bad, because stdout carries the report, and nothing else (ADR-0023).
- Bad, because the extension's task shows stdout in a terminal: the person would read JSON.

#### 2. A pipe or a file descriptor

- Good, because nothing is written to disk, and the reader is woken as each event arrives.
- Bad, because a VS Code task does not let the extension open an extra pipe to the process
  it starts.
- Bad, because an inherited file descriptor beyond the standard three is awkward on
  Windows.

#### 3. A file, `--events PATH`

- Good, because it works from a task, on every platform, and anything that can follow a
  file can read it.
- Good, because a run can be looked at afterwards, as it went.
- Bad, because the reader polls or watches the file, and must leave a line not yet ended.

### The contract

#### 1. Part of the report's schema

- Good, because there is one version to check.
- Bad, because a change to the events alone would change the report's version, which the
  GitHub Action, `impact` and `status` check.

#### 2. A schema of its own, referring to the report's

- Good, because the events and the report change on their own, and `run.started` says
  which version of the report its elements follow.
- Good, because an element is defined once, in the report's schema.
- Neutral, because a validator resolves one schema's references into the other.

### When a skip is decided

#### 1. As soon as a cause fails

- Good, because a cascade of skips shows at once.
- Bad, because `blocked_by` could name fewer causes than the report does.

#### 2. Once every supporter is decided

- Good, because every event agrees with the report.
- Bad, because a skipped element may be decided after steps that have nothing to do with
  it: the engine takes the elements in topological order, and an element it reaches later
  may be called first.

## More Information

- Issue #169, the Run panel's request; #174, calling independent steps together.
- [ADR-0011](0011-json-report-is-the-machine-readable-contract.md), the report as the
  contract; [ADR-0021](0021-execution-semantics.md), statuses and `blocked_by`;
  [ADR-0023](0023-the-command-line.md), stdout and stderr, which this record amends with
  one more output, an option named after what it holds, as that record's outputs are.
- [`events.md`](../events.md) describes every event.
