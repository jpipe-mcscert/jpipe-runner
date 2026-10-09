---
status: accepted
date: 2026-10-09
decision-makers: Sébastien Mosser
---

# ADR-0011: The JSON report is the machine-readable contract

## Context and Problem Statement

v3 had one output, a coloured table framed by ASCII banners, and programs read it anyway.
The GitHub Action recovered the result by string surgery on the runner's standard output
(`tail -n +10` to skip a nine-line banner, a `sed` keyed on the logo's first line, another
to strip the colour codes), so any change to the banner silently broke its pull-request
comment (#132). An exception raised while importing a step library escaped the table
altogether.

v4 has two more consumers on the way. The Action is to be rebuilt on a report it can parse
(MB1, #132), and `jpipe-runner status` is to compare the artifacts recorded by an earlier
run with the files as they are now (#146). Both need what a run concluded as data, and
they will be written in other repositories, or against reports written by other versions
of the runner. Neither can follow a format that changes without notice.

M4 left a `RunResult` behind each run, but only for a run that got as far as validation:
a model the loader refuses and libraries that cannot be imported end in an exception, with
no result at all. And a `RunResult` holds live objects, steps and exceptions, that no
format can carry as they are.

What should a run's machine-readable output be, what should it contain, and how should it
evolve?

## Decision Drivers

- **A program never parses text written for people.** Messages, banners and layout change.
- **Every way a run ends is reported**, including the ways that end before any step runs:
  a CI pipeline needs to know why nothing ran.
- **It is about what was validated**: which claims hold, which steps judged them, what
  they read and produced. Not about how a step receives its inputs.
- **Deterministic**, so that a report can be pinned by a golden file (#124), compared with
  `diff`, and archived with the artifacts it records.
- **Consumers in other repositories keep working** when the runner adds to the report.

## Considered Options

1. A JSON report of our own, built from a report model, described by a versioned JSON
   Schema shipped in the package.
2. SARIF, the format GitHub code scanning reads.
3. JUnit XML, the format CI tools display as test results.
4. Keep the text output, and make its layout stable.

## Decision Outcome

Chosen option: **1, a JSON report with a versioned schema**, because the other formats
cannot hold an argument: SARIF holds findings about source locations, JUnit XML a flat
list of test cases, and neither has elements that support one another, a verdict that
follows from them, or the artifacts an evidence observed.

**One report model, for every way a run ends.** A `RunReport` is plain data, built from a
`RunResult`, from the `InvalidJustificationError` of a refused model, or from the
`LibraryLoadError` of libraries that cannot be imported. Every renderer is a pure function
of it: the text report, the JSON report and the diagram. When nothing ran, the verdict is
`invalid`, and the diagnostics say why.

**The report lists every element of the model**, each after the elements that support it,
with:

- its id, label, kind, `aliases` and the ids of the elements it `supports`. The report is
  self-contained: the argument can be redrawn, and the claims above a changed artifact
  found (#146), without the model's file;
- its `status` (null when nothing ran), `reason`, `blocked_by` (the root causes,
  ADR-0021) and whether its step `ran`;
- `bound_to`, the step as `module.function`, and `bound_by`, the step's ids that designate
  the element (ADR-0007). On a composed model they answer "which of my ids bound this?";
- what the step declares: the paths it `observes`, the variables it `consumes` and
  `produces`. Validation checks these declarations, and they let a reader see the
  dataflow, even of a run that validation stopped;
- what the step `produced`, and the `artifacts` it observed.

Then come every diagnostic, in the order found, and a summary.

**What #122 and #145 first proposed, and why it changed:**

- `"status": "failed"` became `verdict`, with ADR-0021's values (`pass`, `fail`, `skip`,
  and `invalid` when nothing ran).
- `bound_by` is a list: a step may name an element by several ids (ADR-0007).
- `bound_to` names the step `module.function`, as the rest of the report does (ADR-0020),
  rather than the bare function name.
- An artifact does not name the parameter it was passed as (`declared_as`). How a step
  receives a file is the library's business; the report says what was observed: the
  file's `path`, whether it was `reachable`, its `sha256` and its `size`. What the step
  declared is in `observes`.

**Validation's warnings are not listed apart.** There is one list of diagnostics,
validation's first, then each element's in the order run. Each has its severity, and
`strict` says whether warnings were counted as errors.

**Values that are not JSON are written, not refused.** A produced value is
`{"value": ...}` when it is JSON as it is, and `{"repr": ..., "type": ...}` otherwise (a
`Path`, a `datetime`, an object, a float that is not finite). Refusing would fail a run
over its report; a new diagnostic code would be noise for a `Path`, a legitimate value.
The wrapper makes the two forms impossible to confuse.

**A traceback is structured.** The diagnostic of a step that raised (`JP022`) or of a
library that failed to import (`JP020`) carries its exception, as frames (file, line,
function, source line), the exception's type and message, and the exception it was
raised from. It is never Python's formatted text, which differs between Python versions.
Frames are trimmed to the user's code, with paths relative to where the runner runs. To
carry it, the traceback moved onto the `Diagnostic`, where M4 had kept it beside it
(`ElementResult.error`, `LibraryLoadError.tracebacks`).

**Deterministic.** No time, duration or host name; no runner version, which would change
every golden report at every release, and can come back as an optional field; paths
relative to where the runner runs; fields in a fixed order.

**Versioned by `schema_version`**, `"1.0"` first. A minor version only adds optional
fields, and a consumer ignores the fields it does not know; renaming or removing a field,
or changing its meaning, is a new major version. The schema, `report.schema.json`, ships
in the package and is strict (`additionalProperties: false`), so the runner cannot emit a
field it does not document.

### Consequences

- Good, because the Action and `status` read fields, never layout, and can validate what
  they read.
- Good, because a run that stopped before any step ran is reported like any other, with
  its codes.
- Good, because a golden file pins a scenario's whole behaviour in one assertion (#124).
- Good, because the text report is free to change: it is not a contract.
- Bad, because the schema is a second description of the report, to keep in step with the
  code; a test checks every scenario's report against it.
- Bad, because a value that is not JSON reaches a consumer only as its `repr`.
- Neutral, because the report carries the step's declarations as well as the run's
  outcome, which makes it longer than the outcome alone.

### Confirmation

- `tests/unit/test_json_report.py` checks the report of every scenario, whichever way its
  run ends, against the schema; that two runs give the same report; and how values and
  tracebacks are written.
- `tests/unit/test_report_schema_doc.py` recomputes the examples of
  [`report-schema.md`](../report-schema.md), and checks that every field of the schema is
  documented there.
- From #124, the golden reports of `tests/e2e/scenarios/` pin each scenario's whole report.

## Pros and Cons of the Options

### 1. Our own JSON, with a versioned schema

- Good, because it can say everything a run concludes: the argument, the verdict, the
  root causes, the bindings, the artifacts.
- Good, because JSON Schema lets consumers validate it, and the runner check itself.
- Bad, because no tool reads it out of the box: the Action has to.

### 2. SARIF

- Good, because GitHub code scanning displays it.
- Bad, because its results are findings at source locations: an element of an argument,
  its status and what supports it have no place in it.
- Bad, because it is verbose, and its tooling is about static analysis.

### 3. JUnit XML

- Good, because every CI system displays it.
- Bad, because it is a flat list of test cases: no support between elements, no root
  cause, no artifacts.
- Neutral, because it could be added later as another renderer of the same report model.

### 4. A stable text output

- Good, because there is one output to maintain.
- Bad, because it is what v3 did, and what broke the Action.
- Bad, because the layout could never improve for the people who read it.

## More Information

- #122 (this decision), #145 (artifacts), #121 (the report model), #132 (the Action),
  #146 (staleness), #124 (golden reports).
- [ADR-0007](0007-binding-resolution.md), binding; [ADR-0019](0019-evidence-observes-files.md),
  artifacts; [ADR-0020](0020-importing-step-libraries.md), step names;
  [ADR-0021](0021-execution-semantics.md), statuses and the verdict.
- [`report-schema.md`](../report-schema.md), the reader's reference.
