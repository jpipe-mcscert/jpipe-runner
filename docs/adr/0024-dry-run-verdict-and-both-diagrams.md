---
status: accepted
date: 2026-10-09
decision-makers: Sébastien Mosser
---

# ADR-0024: A dry run validates and is `valid`; the report records both diagrams

## Context and Problem Statement

`--dry-run` is meant to check that a step library fits its model without calling any
step: in a pull request, before the artifacts the evidence observes exist, or simply to
see what validation reports. v3 had the flag, and got its outcome wrong: a dry run ran
validation, then reported the justification as `PASS`, although nothing had been judged.

The report of ADR-0011 has four verdicts, and none fits a dry run that found nothing
wrong. `pass` says every element passed, which nothing checked. `skip` says something was
skipped and nothing failed, and `--strict` turns it into a failure (ADR-0021). `invalid`
says validation stopped the run, which it did not.

M5 also drew a justification in two views (ADR-0022): the argument with the run over it,
and its dataflow. The command line can draw both in one run (ADR-0023), but the report
has one field, `diagram`, to say where a diagram was written.

Schema 1.0 has not been released: no consumer reads it yet.

## Decision Drivers

- **A verdict never claims what was not checked.** v3's dry run did.
- **A dry run is useful to a program**, such as the Action on a pull request: it needs
  the report, with the bindings and the declarations, and an exit code.
- **The report says where everything the run wrote is**, as data.
- **Change the contract before it is released**, not after.

## Considered Options

For the dry run:

1. A fifth verdict, `valid`.
2. The verdict `pass`, as v3 did.
3. No report: a dry run prints validation's diagnostics and sets the exit code.

For the second diagram:

1. A `dataflow` field beside `diagram`.
2. A list of diagrams, each with its view.

## Decision Outcome

Chosen options: **a fifth verdict, `valid`**, and **a `dataflow` field**, because they say
what happened in the fields a consumer already reads.

- **`engine.run(..., dry_run=True)` validates and calls no step.** Its `RunResult` has no
  element results, as when validation stops a run, and its verdict is `VALID` when
  validation reported no error, `INVALID` otherwise. A strict dry run counts warnings as
  errors, as a strict run does.
- **The report of a dry run lists every element** with its step and what that step
  declares, its `status` null and `ran` false. So a dry run can draw the declared
  dataflow, and `impact` (#146) can work from the declarations without running anything.
- **`valid` joins the verdicts of the report**, in `report.schema.json` and in
  `report-schema.md`. The command line exits 0 for it (ADR-0023).
- **`dataflow` is the path of the dataflow diagram**, as `diagram` is the path of the
  diagram of the argument; both are null when nothing was drawn, and relative to the
  directory the runner runs in when the diagram is under it.
- **Both are added to schema `1.0`**, which is unreleased: there is nothing to stay
  compatible with. Once 4.0.0 is released, such a change is a new version (ADR-0011).

This amends [ADR-0011](0011-json-report-is-the-machine-readable-contract.md), which listed
four verdicts and one diagram, and
[ADR-0021](0021-execution-semantics.md), which defined the verdicts.

### Consequences

- Good, because a dry run says exactly what it checked, and a program can read it.
- Good, because a run that draws both views records both.
- Bad, because a consumer that matches every verdict must know five.
- Neutral, because `valid` is a verdict no step contributes to: it comes from validation
  alone.

### Confirmation

- `tests/unit/test_engine.py` checks that a dry run calls no step, and its verdicts.
- `tests/unit/test_report.py` and `tests/unit/test_json_report.py` check the report of a
  dry run, and that it matches the schema.
- `tests/unit/test_report_schema_doc.py` checks that `dataflow` is documented.

## Pros and Cons of the Options

### A fifth verdict, `valid`

- Good, because it is true: validation passed, and nothing else was decided.
- Bad, because it changes the contract, which only the release still allows for free.

### `pass`, as v3

- Good, because nothing changes in the schema.
- Bad, because it claims every element passed, and CI would trust it.

### No report

- Good, because nothing changes in the schema.
- Bad, because a program loses the bindings and the declarations, and must parse text to
  learn what validation said.

### A `dataflow` field

- Good, because it is read like `diagram`.
- Bad, because a third view would need a third field.

### A list of diagrams

- Good, because it holds any number of views.
- Bad, because a consumer must search it for the view it wants, and two views are all the
  runner draws (ADR-0022).

## More Information

- #124 (the command line and `--dry-run`); [ADR-0023](0023-the-command-line.md), the
  command line; [ADR-0022](0022-diagrams-follow-the-compiler.md), the two views.
