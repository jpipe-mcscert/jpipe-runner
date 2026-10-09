# The JSON report

The JSON report is what a run concluded, for programs: a CI pipeline, the GitHub Action, a
script. It is a versioned contract
([ADR-0011](adr/0011-json-report-is-the-machine-readable-contract.md)), described by a JSON
Schema that ships in the package,
[`jpipe_runner/schema/report.schema.json`](../src/jpipe_runner/schema/report.schema.json).
The `jpipe-runner` command prints it with `--json`, and writes it to a file with
`--report PATH` ([ADR-0023](adr/0023-the-command-line.md)).

The report is about what was validated: which claims hold, which steps judged them, what
the steps declared they read and produce, and what they actually observed. The text report
a terminal shows is for people, and its layout may change in any release; read this one
instead.

## Versioning

`schema_version` is the first field, `"1.0"`. Within a major version, a minor version only
adds optional fields: **ignore the fields you do not know**. Renaming or removing a field,
or changing what one means, is a new major version.

The schema is strict: it lists every field the runner writes, so the runner cannot add one
without documenting it.

## Determinism

Two runs over the same files give the same report, byte for byte. It holds no time,
duration or host name; every path is relative to the directory the runner runs in, with `/`
as separator; and fields come in a fixed order. The one exception is a produced value whose
own `repr` changes from run to run, such as one that prints the time. A report can be committed, compared with
`diff`, or archived with the artifacts it lists.

## The report

| Field | Type | |
|---|---|---|
| `schema_version` | string | `"1.0"` |
| `justification` | string or null | the justification's name; null if the model was refused before it could be read |
| `verdict` | `pass`, `fail`, `skip`, `invalid` or `valid` | `fail` if an element failed; `skip` if none failed and one was skipped; `pass` if every element passed; `invalid` if nothing ran; `valid` if a dry run found nothing wrong |
| `strict` | boolean | whether the run was strict: validation counted warnings as errors, and the command line failed a skipped verdict (`--strict`) |
| `summary` | object | see [Summary](#summary) |
| `elements` | array | every element of the justification, each after the elements that support it; see [Elements](#elements) |
| `diagnostics` | array | every problem found, in the order found; see [Diagnostics](#diagnostics) |
| `diagram` | string or null | the path of the diagram drawn for the run, if one was |
| `dataflow` | string or null | the path of the dataflow diagram drawn for the run, if one was |

**Every way a run ends has a report.** When nothing ran, the verdict is `invalid` and the
diagnostics say why:

| What stopped the run | `justification` | `elements` | Codes |
|---|---|---|---|
| the model was refused | null | empty | `JP001` to `JP004` |
| a step library could not be imported | the name | every element, unbound, `status` null | `JP020`, `JP021` |
| validation reported an error | the name | every element, with its step, `status` null | see [`rules.md`](rules.md) |

**A dry run** validates the step library and calls no step. When validation reports no
error, its verdict is `valid`, and every element is listed with its step and what that
step declares, with `status` null; the diagnostics are validation's warnings. When
validation reports an error, it is `invalid`, as any other run would be.

The paths of `diagram` and `dataflow` are relative to the directory the runner runs in,
when the diagram was drawn under it.

## Elements

| Field | Type | |
|---|---|---|
| `id` | string | the element's id, as the compiler exports it |
| `label` | string | |
| `kind` | `evidence`, `strategy`, `sub-conclusion` or `conclusion` | its kind in this model: composition may have changed it |
| `aliases` | array of ids | the ids of the elements that composition merged into this one |
| `supports` | array of ids | the elements it supports |
| `status` | `pass`, `fail`, `skip` or null | null when nothing ran |
| `reason` | string or null | why it did not pass: its step's reason, the problem found, or the elements that stopped it |
| `blocked_by` | array of ids | the elements upstream that stopped it, failed or skipped on their own account; empty unless it was skipped because of them |
| `ran` | boolean | whether its step was called |
| `bound_to` | string or null | its step, `module.function`; null if it has none |
| `bound_by` | array of strings | the step's ids that designate this element, as the step names them |
| `observes` | array of strings | the paths and globs its step declares it observes |
| `consumes`, `produces` | arrays of strings | the variables its step declares |
| `produced` | object | the values its step produced, by variable; see [Produced values](#produced-values) |
| `artifacts` | array | the files its step observed; see [Artifacts](#artifacts) |

On a composed model, `aliases` and `bound_by` answer the first question a surprising
binding raises: where did this element come from, and which of its ids did my step name?

## Produced values

Each produced value is an object, in one of two forms:

- `{"value": ...}` when the value is JSON as it is: null, a boolean, a number, a string, or
  a list or a mapping with string keys of such values;
- `{"repr": ..., "type": ...}` otherwise, such as a `Path`, a `datetime`, a set, an object,
  or a float that is not finite. `repr` is Python's `repr()` of the value, made the same on
  every run: a path under the directory the runner runs in is shown relative to it, the
  items of a set are sorted, and an object's address is left out, at any depth. It is cut
  at 1,000 characters. `type` is the value's type, qualified by its module unless it is a
  built-in. A `repr` is for people: do not parse it.

A value is recorded as it was when its step returned: a step that changes a value it
consumes does not change what the report says was produced.

So `.produced.tests_pass.value` reads a value whatever it is, and the presence of `repr`
says that it could not be written as JSON.

## Artifacts

Each file an evidence observed, recorded just before its step was called
([ADR-0019](adr/0019-evidence-observes-files.md)):

| Field | Type | |
|---|---|---|
| `path` | string | the file; for a glob, one entry per file it matched |
| `reachable` | boolean | whether the file could be read |
| `sha256` | string or null | the SHA-256 of its content, as `sha256sum` prints it; null if unreachable |
| `size` | integer or null | its size in bytes; null if unreachable |

An unreachable artifact is listed, and the report's diagnostics include its `JP019`, about
that element. A
glob that matched nothing is listed once, under its pattern. An element whose step was not
called observed nothing, and its `artifacts` is empty; what its step would have observed
is in `observes`.

## Diagnostics

| Field | Type | |
|---|---|---|
| `code` | string | `JPnnn`, which never changes meaning: [`rules.md`](rules.md) lists them all |
| `severity` | `error`, `warning` or `info` | |
| `element` | string or null | the id of the element it is about, if it is about one |
| `message` | string | written for people: it may be reworded in any release |
| `fix` | string or null | what to do about it |
| `traceback` | object or null | the exception behind a `JP022` (a step raised) or a `JP020` (a library failed to import) |

Validation's diagnostics come first, warnings included, then those of each element in the
order run. A strict run reports validation's warnings as errors, and says so in `strict`.

A traceback keeps the frames of the step's or the library's own code, from the outermost
call to where the exception was raised. It is structured rather than Python's text, so that
it reads the same on every Python version:

| Field | Type | |
|---|---|---|
| `exception` | string | its type, qualified by its module unless it is a built-in |
| `message` | string | |
| `frames` | array | each `{"file", "line", "function", "code"}`, with `file` relative to where the runner runs when it is under it |
| `cause` | traceback or null | the exception it was raised from, or while handling |

## Summary

| Field | |
|---|---|
| `elements` | the number of elements |
| `pass`, `fail`, `skip`, `not_run` | how many elements ended so; they add up to `elements` |
| `errors`, `warnings` | how many diagnostics have that severity |

## Examples

The release example of [`end-to-end.md`](end-to-end.md), when the test report records two
failures:

```json
{
  "schema_version": "1.0",
  "justification": "release",
  "verdict": "fail",
  "strict": false,
  "summary": {
    "elements": 4,
    "pass": 1,
    "fail": 1,
    "skip": 2,
    "not_run": 0,
    "errors": 0,
    "warnings": 0
  },
  "elements": [
    {
      "id": "release:e1",
      "label": "The test suite passes",
      "kind": "evidence",
      "aliases": [],
      "supports": [
        "release:s"
      ],
      "status": "fail",
      "reason": "mock/junit.xml: 2 tests failed",
      "blocked_by": [],
      "ran": true,
      "bound_to": "steps.the_test_suite_passes",
      "bound_by": [
        "release:e1"
      ],
      "observes": [
        "mock/junit.xml"
      ],
      "consumes": [],
      "produces": [
        "tests_pass"
      ],
      "produced": {},
      "artifacts": [
        {
          "path": "mock/junit.xml",
          "reachable": true,
          "sha256": "f757d068913cf325e044ecb63ebb0cfb4a1ccedef54f59aee2285dd22097642b",
          "size": 187
        }
      ]
    },
    {
      "id": "release:e2",
      "label": "The changelog is up to date",
      "kind": "evidence",
      "aliases": [],
      "supports": [
        "release:s"
      ],
      "status": "pass",
      "reason": null,
      "blocked_by": [],
      "ran": true,
      "bound_to": "steps.the_changelog_is_up_to_date",
      "bound_by": [
        "release:e2"
      ],
      "observes": [
        "mock/CHANGELOG.md"
      ],
      "consumes": [],
      "produces": [
        "changelog_ok"
      ],
      "produced": {
        "changelog_ok": {
          "value": true
        }
      },
      "artifacts": [
        {
          "path": "mock/CHANGELOG.md",
          "reachable": true,
          "sha256": "d526eb4e878a23ef26ae190031b4efd2d58ed66789ac049ea3dbaf74c9df7402",
          "size": 4
        }
      ]
    },
    {
      "id": "release:s",
      "label": "All release gates pass",
      "kind": "strategy",
      "aliases": [],
      "supports": [
        "release:c"
      ],
      "status": "skip",
      "reason": "not run: release:e1 did not pass",
      "blocked_by": [
        "release:e1"
      ],
      "ran": false,
      "bound_to": "steps.all_release_gates_pass",
      "bound_by": [
        "release:s"
      ],
      "observes": [],
      "consumes": [
        "tests_pass",
        "changelog_ok"
      ],
      "produces": [],
      "produced": {},
      "artifacts": []
    },
    {
      "id": "release:c",
      "label": "Version 2.0 is ready to ship",
      "kind": "conclusion",
      "aliases": [],
      "supports": [],
      "status": "skip",
      "reason": "not run: release:e1 did not pass",
      "blocked_by": [
        "release:e1"
      ],
      "ran": false,
      "bound_to": null,
      "bound_by": [],
      "observes": [],
      "consumes": [],
      "produces": [],
      "produced": {},
      "artifacts": []
    }
  ],
  "diagnostics": [],
  "diagram": null,
  "dataflow": null
}
```

A step that raises (the `exception_handling` scenario):

```json
{
  "schema_version": "1.0",
  "justification": "error_prone",
  "verdict": "fail",
  "strict": false,
  "summary": {
    "elements": 2,
    "pass": 0,
    "fail": 1,
    "skip": 1,
    "not_run": 0,
    "errors": 1,
    "warnings": 0
  },
  "elements": [
    {
      "id": "S1",
      "label": "Divide by number",
      "kind": "strategy",
      "aliases": [],
      "supports": [
        "C1"
      ],
      "status": "fail",
      "reason": "the step raised ZeroDivisionError: division by zero, at steps.py, line 17",
      "blocked_by": [],
      "ran": true,
      "bound_to": "steps.divide_by_number",
      "bound_by": [
        "S1"
      ],
      "observes": [],
      "consumes": [],
      "produces": [
        "result"
      ],
      "produced": {},
      "artifacts": []
    },
    {
      "id": "C1",
      "label": "Validate division result",
      "kind": "conclusion",
      "aliases": [],
      "supports": [],
      "status": "skip",
      "reason": "not run: S1 did not pass",
      "blocked_by": [
        "S1"
      ],
      "ran": false,
      "bound_to": "steps.validate_division_result",
      "bound_by": [
        "C1"
      ],
      "observes": [],
      "consumes": [
        "result"
      ],
      "produces": [],
      "produced": {},
      "artifacts": []
    }
  ],
  "diagnostics": [
    {
      "code": "JP022",
      "severity": "error",
      "element": "S1",
      "message": "the step raised ZeroDivisionError: division by zero, at steps.py, line 17",
      "fix": "Return Fail(reason) when the check does not hold: an exception says the step itself is broken.",
      "traceback": {
        "exception": "ZeroDivisionError",
        "message": "division by zero",
        "frames": [
          {
            "file": "steps.py",
            "line": 17,
            "function": "divide_by_number",
            "code": "return Pass(result=NUMERATOR / DENOMINATOR)"
          }
        ],
        "cause": null
      }
    }
  ],
  "diagram": null,
  "dataflow": null
}
```

A model the loader refuses (the `circular_dependency` scenario):

```json
{
  "schema_version": "1.0",
  "justification": null,
  "verdict": "invalid",
  "strict": false,
  "summary": {
    "elements": 0,
    "pass": 0,
    "fail": 0,
    "skip": 0,
    "not_run": 0,
    "errors": 1,
    "warnings": 0
  },
  "elements": [],
  "diagnostics": [
    {
      "code": "JP004",
      "severity": "error",
      "element": "S1",
      "message": "the relations form a cycle: 'S1' -> 'S2' -> 'S1'",
      "fix": "An element cannot support itself, even indirectly: remove one of these relations.",
      "traceback": null
    }
  ],
  "diagram": null,
  "dataflow": null
}
```
