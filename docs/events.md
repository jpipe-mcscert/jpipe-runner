# The events of a run

A run can tell a program what it is doing while it runs: which step is about to be called,
and how each element ended, as soon as it is decided. The IDE's Run panel uses this to
colour each element of the diagram as the run goes, instead of waiting for the report.
`jpipe-runner --events PATH` writes these events to `PATH`
([ADR-0030](adr/0030-a-run-streams-its-events.md)).

The events **preview the JSON report**, described in [`report-schema.md`](report-schema.md),
and the report stays the authority. An element in an event is the same object as in the
report, so one piece of code reads both. A JSON Schema that ships in the package,
[`jpipe_runner/schema/events.schema.json`](../src/jpipe_runner/schema/events.schema.json),
describes them, and refers to the report's schema for an element and a diagnostic. The
words this page uses, [status](concepts.md#status), [verdict](concepts.md#verdict) and the
others, are defined in [`concepts.md`](concepts.md).

## A run, as it goes

Here is the [release example](end-to-end.md), when the test report records two failures:

```console
$ jpipe-runner --library steps.py --events run.jsonl --report report.json justification.json
Justification: release
  Version 2.0 is ready to ship

  ✘ Evidence    The test suite passes         # release:e1
      steps.the_test_suite_passes: mock/junit.xml: 2 tests failed
      observed mock/junit.xml (sha256 f757d068913c…, 187 bytes)
  ✔ Evidence    The changelog is up to date   # release:e2
  - Strategy    All release gates pass        # release:s
      not run: release:e1 did not pass
  - Conclusion  Version 2.0 is ready to ship  # release:c
      not run: release:e1 did not pass

4 elements (1 failed, 2 skipped, 1 passed)
verdict: fail
```

While it ran, `run.jsonl` received one line per event:

```jsonl
{"event": "run.started", "seq": 0, "elapsed_ms": 0, "schema_version": "1.0", "report_schema_version": "2.0", "justification": "release", "elements": ["release:e1", "release:e2", "release:s", "release:c"], "strict": false, "dry_run": false}
{"event": "validation.ended", "seq": 1, "elapsed_ms": 1, "passed": true, "diagnostics": []}
{"event": "diagram.drawn", "seq": 2, "elapsed_ms": 71, "path": "/tmp/jpipe-runner-i7ba5753/diagram.svg"}
{"event": "element.started", "seq": 3, "elapsed_ms": 71, "id": "release:e1"}
{"event": "source.observed", "seq": 4, "elapsed_ms": 71, "id": "release:e1", "source": "mock/junit.xml", "reachable": true}
{"event": "element.decided", "seq": 5, "elapsed_ms": 71, "element": {"id": "release:e1", "label": "The test suite passes", "kind": "evidence", "aliases": [], "supports": ["release:s"], "status": "fail", "reason": "mock/junit.xml: 2 tests failed", "blocked_by": [], "ran": true, "bound_to": "steps.the_test_suite_passes", "bound_by": ["release:e1"], "observes": ["mock/junit.xml"], "sources": ["mock/junit.xml"], "consumes": [], "inputs": {}, "produces": ["tests_pass"], "produced": {}, "artifacts": [{"path": "mock/junit.xml", "declared": "mock/junit.xml", "reachable": true, "sha256": "f757d068913cf325e044ecb63ebb0cfb4a1ccedef54f59aee2285dd22097642b", "size": 187}], "observations": []}, "diagnostics": []}
{"event": "element.started", "seq": 6, "elapsed_ms": 71, "id": "release:e2"}
{"event": "source.observed", "seq": 7, "elapsed_ms": 72, "id": "release:e2", "source": "mock/CHANGELOG.md", "reachable": true}
{"event": "element.decided", "seq": 8, "elapsed_ms": 72, "element": {"id": "release:e2", "label": "The changelog is up to date", "kind": "evidence", "aliases": [], "supports": ["release:s"], "status": "pass", "reason": null, "blocked_by": [], "ran": true, "bound_to": "steps.the_changelog_is_up_to_date", "bound_by": ["release:e2"], "observes": ["mock/CHANGELOG.md"], "sources": ["mock/CHANGELOG.md"], "consumes": [], "inputs": {}, "produces": ["changelog_ok"], "produced": {"changelog_ok": {"value": true}}, "artifacts": [{"path": "mock/CHANGELOG.md", "declared": "mock/CHANGELOG.md", "reachable": true, "sha256": "d526eb4e878a23ef26ae190031b4efd2d58ed66789ac049ea3dbaf74c9df7402", "size": 4}], "observations": []}, "diagnostics": []}
{"event": "element.decided", "seq": 9, "elapsed_ms": 72, "element": {"id": "release:s", "label": "All release gates pass", "kind": "strategy", "aliases": [], "supports": ["release:c"], "status": "skip", "reason": "not run: release:e1 did not pass", "blocked_by": ["release:e1"], "ran": false, "bound_to": "steps.all_release_gates_pass", "bound_by": ["release:s"], "observes": [], "sources": [], "consumes": ["tests_pass", "changelog_ok"], "inputs": {"tests_pass": {"variable": "tests_pass", "produced_by": "release:e1"}, "changelog_ok": {"variable": "changelog_ok", "produced_by": "release:e2"}}, "produces": [], "produced": {}, "artifacts": [], "observations": []}, "diagnostics": []}
{"event": "element.decided", "seq": 10, "elapsed_ms": 72, "element": {"id": "release:c", "label": "Version 2.0 is ready to ship", "kind": "conclusion", "aliases": [], "supports": [], "status": "skip", "reason": "not run: release:e1 did not pass", "blocked_by": ["release:e1"], "ran": false, "bound_to": null, "bound_by": [], "observes": [], "sources": [], "consumes": [], "inputs": {}, "produces": [], "produced": {}, "artifacts": [], "observations": []}, "diagnostics": []}
{"event": "run.ended", "seq": 11, "elapsed_ms": 73, "verdict": "fail", "exit_code": 1, "summary": {"elements": 4, "pass": 1, "fail": 1, "skip": 2, "not_run": 0, "errors": 0, "warnings": 0}, "report": "report.json", "diagram": null}
```

Once validation has ended, the runner draws the diagram, which takes most of this short
run's time, and `diagram.drawn` says where: in a directory of the system's temporary
directory, whose name changes from one run to the next. `release:e1` and `release:e2`
each start, observe their file, which `source.observed` says was reached, then are decided. `release:s` and `release:c`
are decided without starting: their step is not called, since `release:e1`, which they
depend on, failed. The last line gives the verdict, the exit code, and the report to read
for the rest.

## Reading the file

The file is **JSON Lines**: one JSON object per line, in UTF-8, each line ending with
`\n`. It is opened when the command starts, and emptied once the step libraries are
imported and no output names a file the run observes
([ADR-0035](adr/0035-an-output-never-overwrites-what-the-run-observes.md)); the first
events are written then. From then on, each line is written whole and flushed as soon as
its event happens, so a program can follow the file while the run goes on. Read only
whole lines, those that end with `\n`: while the run goes on, the last line may still be
in the middle of being written. A line holds no line break, whatever a label or a message
holds: the characters some readers take for one, `U+0085`, `U+2028` and `U+2029`, are
escaped as JSON escapes `\n`.

**Order.** `seq` numbers the events from 0, in the order written. What the order promises
is this, and nothing more:

- `run.started` comes first, and `run.ended` last;
- `validation.ended` comes before any element's event;
- `diagram.drawn`, when there is one, comes after `validation.ended` and before any
  element's event;
- an element is decided after every element that supports it;
- an element that starts is decided after it starts;
- the sources an element observes come between its `element.started` and its
  `element.decided`, one `source.observed` each, in the order its step declares them.

The events of two elements may come in any order, and one element's may come between
another's `element.started` and `element.decided`: do not count on the elements coming in
the order of `run.started`'s `elements`, or one at a time. Today the runner calls one step
at a time, but a later one may call independent steps together
([#174](https://github.com/jpipe-mcscert/jpipe-runner/issues/174)), with the same events.

**Time.** `elapsed_ms` is the number of milliseconds since the file was opened, on a clock
that never goes back. It makes the events, unlike the report, differ from one run to the
next.

**The end.** A stream without `run.ended` is that of a run still under way, or of one
that was stopped. Once `run.ended` is written, the report it names is written, and printed
on stdout. A justification, a step library or a python path that cannot be read at all,
such as a missing file, stops the command with exit code 4 and no report, so its stream
ends without `run.ended`, and stderr says why; so does a report that cannot be printed.

## Versioning

`run.started` gives two versions. `schema_version`, `"1.0"`, is the version of the events.
`report_schema_version`, `"2.0"`, is the version of the
[report's schema](report-schema.md#versioning), which the elements and the diagnostics of
the events follow. Within a major version, a minor version only adds optional fields, or
events: **ignore the fields and the events you do not know**. Renaming or removing a
field or an event, or changing what one means, is a new major version.

| Version | Runner | Changed |
|---|---|---|
| 1.0 | 4.1.0 | |

The schema is strict: it lists every field the runner writes, so the runner cannot add one
without documenting it.

## The events

Every event starts with the same three fields:

| Field | Type | |
|---|---|---|
| `event` | string | what happened: one of the events below |
| `seq` | integer | the event's place in the file: 0 for the first, then one more for each |
| `elapsed_ms` | integer | milliseconds since the file was opened |

### `run.started`

The model was read, or refused, before the step libraries are imported. It reaches the
file once they are, with the events that followed it: until then, the file may be one the
run must not touch.

| Field | Type | |
|---|---|---|
| `schema_version` | string | `"1.0"`, the version of the events |
| `report_schema_version` | string | `"2.0"`, the version of the report's schema that elements and diagnostics follow |
| `justification` | string or null | the justification's name; null if the model was refused |
| `elements` | array of strings | every element's id, each after the elements that support it, as the report lists them; empty if the model was refused |
| `strict` | boolean | whether the run is strict (`--strict`) |
| `dry_run` | boolean | whether the run is a dry run (`--dry-run`), which calls no step |

### `validation.ended`

Validation is over. The steps run next, if it passed and the run is not a dry run. A run
whose model was refused, or whose step libraries could not be imported, validates nothing,
and has no `validation.ended`.

| Field | Type | |
|---|---|---|
| `passed` | boolean | whether validation reported no error |
| `diagnostics` | array | what validation reported, each a [diagnostic](report-schema.md#diagnostics) as the report writes it |

### `diagram.drawn`

The run's diagram was drawn before its first step, as a dry run of the same command would
draw it: the dataflow, every element without a status, in SVG
([ADR-0032](adr/0032-a-run-previews-its-diagram.md)). A program that follows the run
colours it as elements are decided. A status never moves a node, so the drawing lines up
with the diagram `--diagram` asks for, which `run.ended` names when the run is over.

The drawing is a file of its own, in a directory the runner makes in the system's
temporary directory, never the `--diagram` file, which holds only the run's own diagram.
**The runner deletes it once the run has ended**, after `run.ended` is written, whatever
ended the run: read it as soon as the event arrives. A run that ends quickly may delete it
before a program gets to it; the drawing then has no use, and the program shows the
`--diagram` file named by `run.ended`, if there is one.

It is written once, when validation passed and the run calls its steps, whether
`--diagram` is given or not. A dry run writes no such event. A drawing that cannot be made,
because Graphviz's `dot` is not installed or for any other reason, is logged on stderr, and
changes nothing else: the event is not written, and the run goes on. So is a drawing an
evidence would observe, when the temporary directory is in the project (`TMPDIR`) and one
of its globs designates the drawing: drawn there, it could change what that evidence
receives. A drawing that cannot be deleted at the end, on Windows because a program still
has it open after a second of trying, is a warning, and changes nothing either.

In the drawing, an element's node has the element's id as its SVG `id`. A source's node,
whose name may hold characters an `id` cannot, has none: its `<title>` is `artifact `
followed by the source, as `source.observed` names it, such as `artifact mock/junit.xml`.

| Field | Type | |
|---|---|---|
| `path` | string | the absolute path of the drawing, an SVG file, deleted once the run has ended |

### `element.started`

Every element that supports this one passed, and its step is about to be called. The files
it observes are observed first: if one cannot be reached, the step is not called, and the
element fails with `JP019`. An element decided without its step, because it is not bound
or because an element it depends on did not pass, does not start.

| Field | Type | |
|---|---|---|
| `id` | string | the element's id |

### `source.observed`

A source the element's step declares it observes was observed: a file, a glob, a value in
a JSON file, an environment variable, or what an observable of the step library observes.
One is written for each source the step declares, in the order it declares them, once
they are all observed and before the step is called: a program can mark each source as the
diagram does, ✔ or ⚠, while a slow step runs. If one is not reachable, the step is not
called, and the element is decided next, failed with `JP019`. The element's
`element.decided` holds what was observed, as the report will write it.

| Field | Type | |
|---|---|---|
| `id` | string | the id of the element whose step observes it |
| `source` | string | the source, as the element's `sources` name it: `mock/junit.xml`, `build/*.xml`, `package.json#/version`, `env:CI` |
| `reachable` | boolean | whether it was reached: a file that exists and can be read, a glob that matches files that all can, a value the pointer designates, a variable that is set |

### `element.decided`

An element is decided: its status is known. Every element of a run that calls its steps
is decided once; in a run that calls none, no element is decided.

| Field | Type | |
|---|---|---|
| `element` | object | the element, as the report will write it: see [Elements](report-schema.md#elements) |
| `diagnostics` | array | what running the element reported, each a [diagnostic](report-schema.md#diagnostics) as the report will write it |

### `run.ended`

The run is over, the report and the diagram are written: the last event.

| Field | Type | |
|---|---|---|
| `verdict` | string | the run's [verdict](report-schema.md#the-report) |
| `exit_code` | integer | the command's [exit code](cli.md#exit-codes) |
| `summary` | object | how many elements ended in each status, and how many diagnostics of each severity: see [Summary](report-schema.md#summary) |
| `report` | string or null | the path of the JSON report, relative to the directory the runner ran in; null if none was written |
| `diagram` | string or null | the path of the diagram, as the report gives it; null if none was drawn |

A run that does not call its steps still has a stream: a dry run writes `run.started`,
`validation.ended` and `run.ended`; a refused model, `run.started`, with no elements, and
`run.ended`.

## When the file cannot be written

A file that cannot be opened, for instance in a directory that cannot be created, stops
the command before anything runs, with exit code 4. A file that a step observes is a usage
error once the step libraries are imported, and is left as it was
([`cli.md`](cli.md#outputs)). Once the run has started, an event
that cannot be written is logged on stderr, nothing more is written, and the run goes on to
its report: the command then exits with code 4 ([`cli.md`](cli.md#exit-codes)).
