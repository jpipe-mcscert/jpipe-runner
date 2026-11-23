---
status: accepted
date: 2026-11-23
decision-makers: Sébastien Mosser
---

# ADR-0039: An incremental run reruns what changed since a report, and reuses the rest

## Context and Problem Statement

A run calls every step of the library, whatever changed since the last one. A pull request
that touches one file of a large project reruns every test suite, scanner and build the
argument rests on. `jpipe-runner impact` and `jpipe-runner status`
([ADR-0025](0025-impact-and-staleness.md)) already say what a change reaches, and what has
changed since a run, but neither runs a step: #153 asked for a run that does only what
the change requires.

A status depends on every supporter's: an element runs only once all its supporters passed
([ADR-0021](0021-execution-semantics.md)). In the release example, a change to
`CHANGELOG.md` reaches the evidence `e2`, the strategy `s` and the conclusion `c`, but `s`
also consumes `tests_pass`, which `e1` produces, and which the change does not reach. To
judge `s` without running `e1`, the run needs what `e1` concluded and produced last time.

The JSON report ([ADR-0011](0011-json-report-is-the-machine-readable-contract.md)) records
that: each element's status, reason and `blocked_by`, its produced values, as JSON or as
their `repr` ([ADR-0033](0033-a-value-is-recorded-as-it-was-seen.md)), the SHA-256 of each
file it observed, and its diagnostics.

What should be run again, what can be taken from the last run, and how does the report say
which is which?

## Decision Drivers

- The verdict is the whole argument's, as a full run's would be when nothing else changed.
- Nothing is reused that may have changed: a step's files, its code, its declarations, or
  the model.
- The baseline is given, not guessed.
- A run with nothing changed reports what the baseline reported.
- The report says what was reused, for a program as for a person.

## Considered Options

1. Rerun what changed since a report given with `--incremental`, and reuse the rest.
2. Run only what a set of changed files or a git revision reaches, and judge nothing else.
3. Run what changed and every supporter it needs.

## Decision Outcome

Chosen option: **1, rerun what changed since a report, and reuse the rest**, because it
alone judges the whole argument while running only what changed.

**The option.** `--incremental REPORT` names the JSON report of an earlier run, the
baseline, read before anything runs. Everything else works as in a full run: `--report`,
which may name the same file, `--json`, `--diagram`, `--events`, `--jobs`, `--strict`.
`--incremental` with `--dry-run` is a usage error. A baseline that does not exist is no
error: the run is full, with a warning, so that the first run of a pipeline needs no
special case. A file that is not a report of a version this runner reads is a usage error
(exit code 2), and one that cannot be read exits 4.

**What reruns.** Validation runs as in any run. Then an element reruns when:

- the baseline cannot stand for this run: it ran no step (`invalid`, `valid`), it is of
  another justification, or its elements, their kinds or their `supports` differ from the
  model's: then every element reruns;
- its step's declarations differ from the baseline's: the step it is bound to, the ids that
  bind it, what it observes, consumes and produces, and where each input comes from;
- its step's library changed: the report records, for each bound element, the SHA-256 of
  the file that declares its step (`library_sha256`, new in report 2.1); one the baseline
  does not record, or a step with no file, counts as changed;
- something it observed changed since, as `jpipe-runner status` finds it: a file changed,
  vanished, appeared or was added to a glob, or an environment variable changed; or what it
  observed cannot be checked from the report, because it is hidden or observed by the
  library's own observable;
- it is above an element that reruns: everything an element supports, up to the
  conclusion;
- a step that reruns consumes a value it produced, and the baseline holds that value only as
  its `repr`: a `repr` cannot be passed to a step.

The rest is **reused**: the element is decided as the baseline decided it, before any step
it supports runs, with the baseline's status, reason, `blocked_by`, `ran`, observed files
and diagnostics, tracebacks included. Its produced values, which the baseline holds as JSON,
are passed to the steps that rerun and consume them, as JSON decodes them: a tuple comes
back as a list. Since what reruns is closed upwards, an element reused has only reused
supporters, and the baseline's decision still holds.

**The report** says which is which. Each element has `reused`, true when it was taken from
the baseline; a top-level `selection`, null for a full run, holds the baseline, as given on
the command line, and, for each element that reran, why, in topological order. The verdict
and the exit code are those of a full run, over every element, reused or not. The text
report marks a reused element, and says how many reran; the events write each element as
the report does, so `element.decided` carries `reused`.

### Consequences

- Good, because a change to one file reruns the evidence that observes it, and what that
  evidence supports, and nothing else.
- Good, because the report of an incremental run is complete: it can be the baseline of the
  next one, and `status` reads it as any other.
- Good, because a missing baseline is a full run, so a pipeline caches the report and passes
  it, whether the cache was restored or not.
- Bad, because a step that reads a file it does not declare, or a value from outside the
  run, is reused while that changed: the rerun is only as good as the declarations, as
  `impact` and `status` are.
- Bad, because the library's file is a coarse fingerprint: changing one step reruns every
  step the file declares, and a change to a module the step imports reruns nothing.
- Bad, because a value reused from JSON has JSON's types, which a step written for a tuple
  or a `Path` may not expect; a value only a `repr` records reruns its producer instead.

### Confirmation

- `tests/unit/test_incremental.py` checks each reason to rerun, the closure upwards, the
  producers rerun for a `repr`, and that a run with nothing changed, given its own report,
  reruns nothing and reports what the baseline reported.
- Every e2e scenario that runs its steps is run again with its golden report as the
  baseline.

## Pros and Cons of the Options

### Rerun what changed since a report

- Good, because the whole argument is judged.
- Bad, because the run trusts the baseline: a report edited by hand is believed.

### Run only what a change reaches

- Good, because it needs no baseline.
- Bad, because an element with a supporter the change does not reach cannot be judged, so
  most of the argument above a change goes unjudged, and the verdict is about a part.

### Run what changed and every supporter it needs

- Good, because nothing is reused.
- Bad, because a change reaches the conclusion, which needs every element: it is the full
  run.

## More Information

Issue #153, which also asked for `--incremental`, reusing the outcome of unchanged evidence.
The report's schema goes to 2.1: `selection` and, for each element, `reused` and
`library_sha256`, all optional to a reader. `impact` and `status` read 2.1 as they read
2.0. The GitHub Action ([ADR-0012](0012-extract-the-github-action.md)) can cache the report
and pass it; that is for its own repository.
