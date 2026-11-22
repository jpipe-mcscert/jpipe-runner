---
status: accepted
date: 2026-11-21
decision-makers: Sébastien Mosser
---

# ADR-0033: A value is recorded as it was when the run saw it, even one that cannot be copied

## Context and Problem Statement

The report records the values a run saw: what each step produced, and what each evidence
observed that is not a file. A step receives the value itself, so the engine records a deep
copy, taken when the step returned or the source was observed: a step that changes a value
it consumes must not change what the report says was produced
([`report-schema.md`](../report-schema.md#elements)). A value that cannot be deep-copied,
such as a lock or an open file, was kept as it was, by reference.

Since `--events` ([ADR-0030](0030-a-run-streams-its-events.md)), an element is written twice:
in its `element.decided` event, when it is decided, and in the report, when the run ends. For
a value kept by reference, the two writes read the object at different times. If a step
produces `threading.Lock()` and the step that consumes it acquires it, the event says
`<unlocked _thread.lock object>` and the report `<locked _thread.lock object>` (#184). The
report alone was already wrong: it claimed to record the value as produced, and recorded it
as it was at the end of the run. Should the report record such a value as produced, or as it
is at the end?

## Decision Drivers

- **The report's promise.** It says a value is recorded as it was when its step returned.
- **The events preview the report.** An element in an event is the element the report will
  write, so that one piece of code reads both.
- **Determinism**, now and once steps run concurrently (#174): what the report says of a
  value must not depend on when it is written.
- **Formatting stays with the reports.** The engine decides nothing about how a value is
  written, beyond what it must take while the value is as produced.

## Considered Options

1. Accept the difference and document it: the report records such a value as it is at the
   end of the run.
2. Record a value that cannot be copied as its `repr` and type, taken when the run saw it.
3. Have the event stream hand the elements it encoded to the report.

## Decision Outcome

Chosen option: **2, record its `repr` and type, taken then**, because it is the only one
that keeps the report's promise for every value, whether or not `--events` is given.

`records.snapshot`, which the engine applies to what a step produced and `artifacts` to what
an evidence observed, returns a deep copy, or, for a value that cannot be copied, an
`Uncopied`: its canonical `repr` and its type, taken at that moment. The JSON report writes an
`Uncopied` as it writes any value that is not JSON, `{"repr": ..., "type": ...}`, so the
report's schema does not change. The canonical `repr` (paths relative to the run's root, sets
sorted, no addresses) moves from `json_report` to `records`, so that the record and the report
make it the same way. The step that consumes the value still receives the object itself.

### Consequences

- Good, because the event and the report write the same thing for every value.
- Good, because the report says what was produced, as it already claimed.
- Good, because the record does not depend on when, or in what order, steps run.
- Neutral, because the engine now takes the `repr` of a value it cannot copy; how the report
  writes it, `{"repr", "type"}`, stays in `json_report`.
- Bad, because the `repr` is taken even when nothing reads the report: one more call to the
  value's `__repr__`, only for a value that cannot be copied.

### Confirmation

`test_engine.py` checks that a lock is recorded as unlocked although it is acquired after
its step returned, and `test_events.py` that a lock a later step acquires reads the same in
its `element.decided` event and in the report.

## Pros and Cons of the Options

### 1. Document the difference

- Good, because nothing changes in the code.
- Bad, because the report records what a later step did to a value, not what was produced.
- Bad, because the event and the report disagree, and which is right depends on timing.

### 2. Record the `repr` and type, taken then

- Good, because it is right for every value, whatever is listening.
- Bad, because a `repr` is taken eagerly for every value that cannot be copied.

### 3. The stream hands its elements to the report

- Good, because the event and the report agree.
- Bad, because it applies only with `--events`: the report would say something else without
  it.

## More Information

Issue #184, raised by the review of #182 (`--events`).
