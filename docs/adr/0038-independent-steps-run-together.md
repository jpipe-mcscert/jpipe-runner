---
status: accepted
date: 2026-11-22
decision-makers: Sébastien Mosser
---

# ADR-0038: Independent steps run together, on threads, when asked

## Context and Problem Statement

A run calls its steps one after another: [ADR-0021](0021-execution-semantics.md) takes the
elements *"in topological order, ties broken by model order"*. Evidence steps are where a
run spends its time, since they run test suites, scanners, linters and builds, and most of
them depend on nothing else in the run. Their order comes from the tie-break, not from the
argument.

The supports relation is a partial order: when `e1` and `e2` support `s`, `s` waits for
both, and nothing orders `e1` and `e2`. Nothing else in the semantics depends on the
sequence:

- an element's status, reason and `blocked_by` depend only on its supporters' results,
  all known once the last of them is decided;
- every value has one producer (`JP009`, `JP014`, `JP025`), and `ValueStore.put` refuses a
  second write, so two steps cannot race on a value;
- the report records each element with what it produced, so results sorted back into
  topological order give the same report ([ADR-0011](0011-json-report-is-the-machine-readable-contract.md)).

The tie-break is still what some libraries rely on, without saying so. If the step of
`e1` writes `build/out.xml` and the evidence `e2` observes it, the library works only
because `e1` comes first in the model. No argument can say so instead: only an evidence
observes, and nothing supports an evidence.

How should independent steps run together, and what does that change for a step library?

## Decision Drivers

- The report does not depend on how many steps ran at a time.
- A library that relies on model order keeps working until its author asks for more.
- The events keep what [ADR-0030](0030-a-run-streams-its-events.md) promised: a causal
  order, which already allows two elements' events to interleave.
- The authoring API, which the compiler co-owns, does not change.
- Most evidence steps wait on a subprocess or on I/O.

## Considered Options

1. Threads, asked for with `--jobs`.
2. Processes, with a pool of interpreters.
3. Keep the sequence.

## Decision Outcome

Chosen option: **1, threads, asked for with `--jobs`**, because a step that waits on a
subprocess or on a file releases the GIL, so threads give most of the speed-up at a small
cost.

**The option.** `--jobs N` runs up to `N` steps at a time; `--jobs auto` runs one per CPU
the process may use (`os.process_cpu_count`, from Python 3.13, otherwise `os.cpu_count`).
The default is `1`, the sequence of ADR-0021. A number that is not a positive integer, or
`auto`, is a usage error (exit code 2). `engine.run` takes `jobs` too, and refuses one
below 1.

**The scheduler.** An element is ready once every element that supports it is decided,
and the ready element first in topological order is taken first. A skip, a pass without a
step, or a step's start happens then, on the thread that runs the run. With one job, the
step is called there, so the elements are decided in ADR-0021's order and the events are
those it wrote. With more, the step goes to a thread of a pool of `N`, which observes its
artifacts, says so, calls the step and hands back what it returned or raised. Everything
else stays on the run's thread: reading the values the step consumes, the listener and
its events, judging the outcome, storing the values and recording the result. The engine
holds no lock, and the listener is called from one thread, as ADR-0030 says.

**The result** lists the elements in topological order whatever the number of jobs, so
the report, the text report and the diagram are the same; only the events, which are not
deterministic, show what ran together. A step's `source.observed` events come while it
runs, as with one job. Nothing in the report or the events records the number of jobs.

**Ctrl-C.** `KeyboardInterrupt` stops the run (ADR-0021). A step already running on a
thread cannot be stopped, so the run starts no other step, and the process waits for
those still running before it exits. The run's thread waits for a step in short slices so
that Ctrl-C reaches it on every platform. A step that raises `KeyboardInterrupt` on its
thread stops the run the same way, and so does an error of the runner itself.

**What a library must not do with `--jobs`** is documented rather than enforced. No step
can opt out of running alongside others:

- **A file one step writes and an evidence observes**: run together, the evidence may read
  it before it is written, and fail with `JP019`, or record the hash of a half-written
  file. Nothing in an argument can make an evidence wait for another step, so the file is
  built before the run, or written and checked by one evidence, which produces what it
  found as a value. Validation cannot see what a step writes, so no rule warns about it.
- **State the process shares**: the working directory (`os.chdir`), `os.environ`, module
  globals. A step passes `cwd=` and `env=` to the command it runs instead. What concurrent
  steps print interleaves on stderr.
- **The main thread**: with more than one job a step does not run there, so
  `signal.signal`, which only the main thread may call, raises in it.
- **A consumed value**: two consumers of one variable receive the same object, as they do
  with one job, where a step that changes it already changes what the next consumer
  receives. Run together, they race. A step must not change what it consumes. The report
  records each value as it was produced ([ADR-0033](0033-a-value-is-recorded-as-it-was-seen.md)),
  so the record is safe either way.

### Consequences

- Good, because the steps the argument leaves independent take the time of the slowest,
  not the sum, once their author asks for it.
- Good, because one report holds whatever the number of jobs: a test runs every scenario
  with four jobs against the golden report written with one.
- Good, because a run with one job is the run of ADR-0021, step for step and event for
  event.
- Good, because the authoring API is unchanged, and so is what the compiler generates.
- Bad, because a step that computes in Python, without waiting, gains nothing: the GIL
  runs one thread at a time.
- Bad, because a library that relies on model order, or on state the process shares,
  breaks with `--jobs`, and nothing but its author's reading of these rules can tell.
- Bad, because a step that hangs keeps the process from exiting after Ctrl-C.

### Confirmation

- `tests/unit/test_concurrent_run.py` checks that independent steps run together, never
  more than `jobs` at a time, that the result is in topological order whatever ends first,
  that one job calls each step on the run's thread, that the listener is told only there,
  and of a source while its step runs, and how an interrupt and a runner bug stop the run.
- `tests/unit/test_execution_properties.py` checks every property of a run, with one job
  and with three.
- `tests/e2e/test_scenarios.py` runs every scenario with `--jobs 4` against the golden
  report written with one job.

## Pros and Cons of the Options

### Threads, asked for with `--jobs`

- Good, because the step libraries are imported once, values pass between steps as they
  are, and the engine keeps one copy of the run's state.
- Bad, because of the GIL, for a step that computes rather than waits.

### Processes, with a pool of interpreters

- Good, because a step that computes runs in parallel.
- Bad, because every worker re-imports the step libraries, which `libraries.imported`
  does by changing `sys.path` and `sys.modules`, every value passed between steps is
  pickled, which an open file or a lock cannot be, and `spawn` on macOS and Windows starts
  each worker from scratch.

### Keep the sequence

- Good, because nothing changes.
- Bad, because a run takes the sum of its steps' times, when the argument says most of
  them are independent.

## More Information

Issue #174. This amends [ADR-0021](0021-execution-semantics.md): with more than one job,
the elements are taken in a partial order, and the result keeps its order. ADR-0030 had
already made the events' order causal for this. The GitHub Action
([ADR-0012](0012-extract-the-github-action.md)) passes options to the command line; giving
it `--jobs` is for its own repository.
