# v4 progress

jpipe-runner v4 is a rewrite from scratch ([ADR-0002](adr/0002-rewrite-from-scratch.md)),
built one [milestone](https://github.com/jpipe-mcscert/jpipe-runner/milestones) at a time.
This page follows the rewrite: where each milestone stands, and what v4 can do so far. It
is updated as each milestone lands.

Since M6, v4 runs as the `jpipe-runner` command. It is not released yet: install it from
this repository (`pip install git+https://github.com/jpipe-mcscert/jpipe-runner`). The
[latest stable release](https://github.com/jpipe-mcscert/jpipe-runner/releases/latest) is
still 3.6.0.

- [`tutorial.md`](tutorial.md) takes an argument from its `.jd` file to a green run (M6).
- [`cli.md`](cli.md) describes every option and exit code of the command (M6).
- [`authoring.md`](authoring.md) is the guide to writing a step library (M2).
- [`end-to-end.md`](end-to-end.md) follows one example through every stage, from the `.jd`
  file to the verdict, and says which stages work today.
- [`design.md`](design.md) describes how the code built so far fits together.
- The [CHANGELOG](../CHANGELOG.md) lists what changes for v3 users.

## Milestones

| Milestone | Status | Issues | ADRs |
|-----------|--------|--------|------|
| M0 Foundation | done | #106–#111, #133 | [0001](adr/0001-consume-compiler-json.md), [0002](adr/0002-rewrite-from-scratch.md), [0003](adr/0003-drop-sphinx-markdown-docs.md), [0004](adr/0004-sonarcloud-quality-gate.md), [0014](adr/0014-trunk-with-milestone-branches.md), [0015](adr/0015-draft-pull-request-per-milestone.md) |
| M1 Model | done | #112 | [0016](adr/0016-hide-the-graph-inside-justification.md) |
| M2 Authoring API | done | #113–#117, #126 | [0005](adr/0005-outcomes-as-return-values.md), [0006](adr/0006-one-decorator-per-kind.md), [0007](adr/0007-binding-resolution.md), [0008](adr/0008-drop-external-variable-injection.md), [0009](adr/0009-separate-registry-from-value-store.md) |
| M3 Validation | done | #118, #119, #128, #143 | [0010](adr/0010-diagnostics-as-data-rules-as-objects.md), [0013](adr/0013-kind-divergence-under-composition.md), [0018](adr/0018-evidence-declares-observed-artifacts.md) |
| M4 Execution | done | #120, #144 | [0019](adr/0019-evidence-observes-files.md), [0020](adr/0020-importing-step-libraries.md), [0021](adr/0021-execution-semantics.md) |
| M5 Reporting | done | #121–#123, #145, #150, #151 | [0011](adr/0011-json-report-is-the-machine-readable-contract.md), [0022](adr/0022-diagrams-follow-the-compiler.md) |
| M6 CLI | done | #124, #125, #127, #146 | [0023](adr/0023-the-command-line.md), [0024](adr/0024-dry-run-verdict-and-both-diagrams.md), [0025](adr/0025-impact-and-staleness.md) |
| M7 Docs | planned | #129, #140, #142 | [0017](adr/0017-document-in-the-milestone-that-builds-it.md) |
| MB0 Action extraction | planned | #130, #131 | 0012 (reserved) |
| MB1 Action v1 | planned | #132 (in `jpipe-runner-action`) | |

What each planned milestone will add:

- **M7 Docs:** a consistency review of the documentation each milestone wrote, the README,
  troubleshooting and the migration guide
  ([ADR-0017](adr/0017-document-in-the-milestone-that-builds-it.md)).
- **MB0, MB1:** the GitHub Action, moved to its own repository and rebuilt on the JSON
  report.

## What v4 can do so far

### M0 Foundation

Nothing a user runs: v3 is frozen at 3.6.0, the v3 code and tests are gone, and the v4
tooling, quality gate and test architecture are in place.

### M1 Model: reading a justification

- Reads the JSON the jPipe compiler emits (`jpipe process -f JSON`) and checks it against
  the compiler's format.
- Refuses a justification that cannot be run, and reports every problem in it at once, each
  with a code: a file that is not JSON or not in the compiler's format (`JP001`), an id or
  alias that designates two elements (`JP002`), a relation to an element that does not
  exist (`JP003`). A template is refused with a message saying why it cannot be run.

### M2 Authoring API: writing a step library

Documented in [`authoring.md`](authoring.md).

```python
from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy


@evidence("release:e1", observes={"log": "build/tests.log"}, produces=["tests_pass"])
def the_test_suite_passes(log: Path) -> Outcome:
    if "FAILED" in log.read_text(encoding="utf-8"):
        return Fail(f"{log} reports a failed test")
    return Pass(tests_pass=True)


@strategy("release:s", consumes=["tests_pass"])
def all_release_gates_pass(tests_pass: bool) -> Outcome:
    return Pass() if tests_pass else Fail("a release gate did not pass")
```

- **One decorator per kind of element:** `@evidence`, `@strategy`, `@sub_conclusion` and
  `@conclusion`. Each takes the ids of the element it implements, one or several, and the
  variables the step consumes and produces. Evidence consumes nothing, and a conclusion
  produces nothing. Conclusions and sub-conclusions are optional: an unbound one takes its
  status from what supports it.
- **A step is a plain function.** Its parameters are the variables it consumes, and it can
  be called in a unit test without the runner. A declaration that cannot be right (no id,
  a parameter that is not consumed, `produces="x"` instead of a list) is an error when the
  library is imported.
- **A step returns an outcome:** `Pass(...)` with the values it produces, `Fail(reason)` or
  `Skip(reason)`. A step that returns `True`, `False` or nothing is reported (`JP017`), with
  the outcome to return instead.
- **Ids bind as the compiler writes them:** an element's id or alias, the id qualified by
  the justification's name, or a unique tail of it (`e_metric` for `rigor:r17:e_metric`).
  This keeps working after composition: a step written against a model still binds once
  that model is assembled or refined. Binding is one to one. An id that designates no
  element (`JP015`) or several (`JP006`), and an element claimed by two functions or a
  function claiming two elements (`JP007`), are reported together.
- **Values are kept per run**, each with the element that produced it, and a step may
  produce `None`.

### M3 Validation: checking a step library against its model

Every check is described in [`rules.md`](rules.md); [`end-to-end.md`](end-to-end.md)
shows what validation reports on the release example.

- **Every problem is reported at once, each with a code and a fix.** A step library is
  checked against its model before any step runs.
  - An error stops the run.
  - A warning is reported, and the run continues: a warning no longer fails a run, as it
    did in v3.
  - A strict run counts warnings as errors.
  - No check can be disabled.
- **What is checked:**
  - Every evidence and strategy has a step (`JP005`).
  - Ids bind one to one (`JP006`, `JP007`, `JP015`).
  - Each step's kind agrees with its element's (`JP016`).
  - Every consumed variable is produced by one step (`JP009`, `JP010`), which supports its
    consumer, directly or not (`JP014`).
  - Every evidence produces a value that another step consumes (`JP012`).
  - Warnings: a strategy ignoring a value its supporters produce (`JP013`), and a value
    nothing consumes (`JP011`).
- **Composition is understood.** A step written against a model before it was refined,
  assembled or unified keeps working where composition changed its element's kind: it is
  a warning (`JP008`), and the step runs as a cross-check.
- **Evidence declares the artifacts it observes**, with
  `observes={"changelog": "CHANGELOG.md"}`: a file or a glob, relative to where the
  runner runs. (M3 also accepted a directory; M4 dropped it,
  [ADR-0019](adr/0019-evidence-observes-files.md).) The step receives each one as a parameter, so a test passes its
  own. An evidence that observes nothing is an error (`JP018`). Documented in
  [`authoring.md`](authoring.md#observing-artifacts).
- **A model whose relations form a cycle is refused when it is loaded** (`JP004`), like
  the other malformed models.
- **[`rules.md`](rules.md) is the reference of every diagnostic code.** It is generated
  from the checks themselves.

### M4 Execution: running a step library

[`authoring.md`](authoring.md#when-the-steps-run) describes what happens when the steps
run; [`end-to-end.md`](end-to-end.md#6-running-the-steps) runs the release example.

- **Steps run supporters first**, each once, in an order that depends only on the model.
  A step receives, by name, the values it consumes and the artifacts it observes. A
  conclusion or sub-conclusion without a step passes when what supports it passes.
- **A failure or a skip stops what it supports.** Everything above an element that did
  not pass is skipped, without being called, and names the element that stopped it,
  however far below. v3 let a skipped step's successors run.
- **The justification's verdict** is `fail` if an element failed, `skip` if none failed
  and one was skipped, and `pass` when everything passed. A skipped justification is not
  a failure (the command line exits 0 for it unless the run is strict).
- **Observed artifacts are checked, recorded and passed.** Before an evidence is called,
  each file it observes is recorded with its path, SHA-256 and size. One that is missing
  or unreadable, or a glob that matches nothing, fails the evidence without calling it
  (`JP019`). An evidence observes files: a directory is refused when the library is
  imported, in favour of a glob of its files.
- **A broken step fails its element, and the run goes on**, so one run reports every
  broken step:
  - an exception, with its traceback from the step's own code (`JP022`);
  - a value that is not an outcome (`JP017`);
  - a `Pass` without a value the step declares (`JP023`); a value it does not declare is
    dropped, with a warning (`JP024`).
- **Step libraries are imported as modules named after their files**, for the run, with
  the python path first on `sys.path`, restored exactly afterwards. A library that fails
  to import is reported at its line (`JP020`), with every other one, rather than as a bare
  traceback (old #75); two libraries with the same name, or one named like another
  module (`json.py`), are refused (`JP021`).

### M5 Reporting: reading what a run concluded

[`end-to-end.md`](end-to-end.md) shows the text report of each run of the release
example, its JSON report and its diagrams;
[`report-schema.md`](report-schema.md) documents the JSON report.

- **Every way a run ends is reported**, including a model that is refused, a step library
  that cannot be imported, and a library that validation stops: what stopped the run, with
  its codes and fixes, and the verdict `invalid`.
- **A text report for people, in the manner of Cucumber.** One line per element, in the
  order run, with a symbol for its status, its kind, its label and its id. An element that
  did not pass says why, and what stopped it; a failed evidence names the files it
  observed. Then each diagnostic with its fix, and for a step or library that raised, its
  traceback from the user's own code; then the summary and the verdict. Colour is used only
  on a terminal, never with `NO_COLOR`.
- **A JSON report for programs**, versioned (`schema_version` 1.0) and described by a
  schema shipped in the package. Each element says what concluded about it, which function
  judged it through which of its ids, what that function declares it observes, consumes
  and produces, the values it produced, and each file it observed with its SHA-256 and
  size. Every diagnostic is listed, with a structured traceback. The report is the same on
  every run over the same files.
- **Diagrams drawn as the jPipe compiler draws them**, with the run over them in the
  compiler's colour-blind-safe palette: green border for a pass, vermillion for a failure,
  dashed grey for a skip. A **dataflow view** adds the files each evidence observes and the
  variables that flow between the steps, and shows in vermillion a variable with no
  producer or no consumer, and a file that could not be read. Only Graphviz's `dot` is
  needed, and the `dot` format not even that.
- **Composed models run end to end**: assembled and unified models, as well as refined ones,
  with libraries written against their sources, and
  [`authoring.md`](authoring.md#libraries-written-for-separate-models) says what such
  libraries need when they run together.

### M6 CLI: running a justification

[`tutorial.md`](tutorial.md) walks through a first run; [`cli.md`](cli.md) describes every
option; [`end-to-end.md`](end-to-end.md#from-the-command-line) ends with the command.

```shell
jpipe-runner --library steps.py --report report.json --diagram release.svg justification.json
```

- **One command runs a justification**: it loads the JSON the compiler wrote, imports the
  step libraries (a file or a glob each), validates them, runs them, and prints the text
  report. `python -m jpipe_runner` is the same command, and imports the same modules.
- **Every output is explicit**: stdout carries the report, and nothing else; `--json`
  prints the JSON report instead of the text one. `--report`, `--diagram` and
  `--dataflow` write the JSON report and the two diagrams, each in the format its suffix
  names, all in one run. An output that cannot be written is refused before any step
  runs.
- **Exit codes a CI pipeline can act on**: 0 the justification holds (or is skipped), 1
  it fails, 2 the command line is wrong, 3 nothing could run, 4 a file could not be read
  or written. `--strict` also fails a skipped justification and counts warnings as
  errors.
- **A dry run** (`--dry-run`) checks a library against its argument without calling any
  step, and reports `valid`.
- **Logs that can be seen**, on stderr: `-v` for what the run does, `-vv` for details,
  `-q` for errors only. `--colour` chooses whether the text report is coloured.
- **What a change reaches**: `jpipe-runner impact --changed PATH` or `--since REF` lists
  the evidence observing changed files and everything above it, without running a step.
- **What has changed since a run**: `jpipe-runner status report.json` compares the files a
  run recorded with the files now, and lists what is stale.
- **Each scenario's whole JSON report is pinned by a golden file**, run through the
  command.

## Gone from v3

- `@jpipe`, `@jpipe_link`, `@skip`, `@contribution` and the `produce` parameter (M2).
  Importing the v3 API says what replaced it.
- Value injection through `--variable` and `--config-file` (M2).
- A step skipped by `@skip` no longer lets what it supports run without its values (M4).
- The Sphinx API documentation and the v3 guides (M0).
- v3's results table and its ASCII banners, which programs had to parse: the text report is
  for people, and programs read the JSON report (M5).
- v3's diagram colours, and its rewriting of `:` into `_` in diagram ids (M5); and the
  `graphviz` Python package, which drew them (M5).
- v3's command-line options that changed meaning or went away (M6): `-v` was
  `--variable` and is now `--verbose`; `-V` is gone; `-o/--output-path`, a directory, and
  `-f/--format` gave way to `--diagram PATH` and `--dataflow PATH`; `--diagram PATTERN`,
  which did nothing, now names the file to draw; `--python-path` no longer defaults to the
  working directory; and the justification no longer has to end in `.json`.
- v3's exit code 1 for every problem (M6), and its dry run that reported a pass.

Step libraries generated by jPipe 2.5.0 still target v3
([#140](https://github.com/jpipe-mcscert/jpipe-runner/issues/140)).
