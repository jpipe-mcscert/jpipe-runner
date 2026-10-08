# v4 progress

jpipe-runner v4 is a rewrite from scratch ([ADR-0002](adr/0002-rewrite-from-scratch.md)),
built one [milestone](https://github.com/jpipe-mcscert/jpipe-runner/milestones) at a time.
This page follows the rewrite: where each milestone stands, and what v4 can do so far. It
is updated as each milestone lands.

There is no command line until M6, so nothing below can be run as `jpipe-runner` yet: it is
the library the command line will be built on. For a working runner, use the
[latest stable release](https://github.com/jpipe-mcscert/jpipe-runner/releases/latest)
(3.6.0).

- [`end-to-end.md`](end-to-end.md) follows one example through every stage, from the `.jd`
  file to the verdict, and says which stages work today.
- [`design.md`](design.md) describes how the code built so far fits together.
- The [CHANGELOG](../CHANGELOG.md) lists what changes for v3 users.

## Milestones

| Milestone | Status | Issues | ADRs |
|-----------|--------|--------|------|
| M0 Foundation | done | #106–#111, #133 | [0001](adr/0001-consume-compiler-json.md), [0002](adr/0002-rewrite-from-scratch.md), [0003](adr/0003-drop-sphinx-markdown-docs.md), [0004](adr/0004-sonarcloud-quality-gate.md), [0014](adr/0014-trunk-with-milestone-branches.md), [0015](adr/0015-draft-pull-request-per-milestone.md) |
| M1 Model | done | #112 | [0016](adr/0016-hide-the-graph-inside-justification.md) |
| M2 Authoring API | done | #113–#117 | [0005](adr/0005-outcomes-as-return-values.md), [0006](adr/0006-one-decorator-per-kind.md), [0007](adr/0007-binding-resolution.md), [0008](adr/0008-drop-external-variable-injection.md), [0009](adr/0009-separate-registry-from-value-store.md) |
| M3 Validation | planned | #118, #119 | 0010, 0013 (reserved) |
| M4 Execution | planned | #120 | |
| M5 Reporting | planned | #121–#123 | 0011 (reserved) |
| M6 CLI | planned | #124 | |
| M7 Docs | planned | #125–#129, #140 | |
| MB0 Action extraction | planned | #130, #131 | 0012 (reserved) |
| MB1 Action v1 | planned | #132 (in `jpipe-runner-action`) | |

What each planned milestone will add:

- **M3 Validation:** checking a step library against its model before running anything.
- **M4 Execution:** running the steps, supporters first.
- **M5 Reporting:** text and JSON reports, and diagrams.
- **M6 CLI:** the `jpipe-runner` command and its exit codes.
- **M7 Docs:** tutorial, authoring guide, CLI and rules reference, migration guide.
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

```python
from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy


@evidence("release:e1", produces=["tests_pass"])
def the_test_suite_passes() -> Outcome:
    if Path("mock/tests.ok").is_file():
        return Pass(tests_pass=True)
    return Fail("mock/tests.ok not found")


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

## Gone from v3

- `@jpipe`, `@jpipe_link`, `@skip`, `@contribution` and the `produce` parameter (M2).
  Importing the v3 API says what replaced it.
- Value injection through `--variable` and `--config-file` (M2).
- The Sphinx API documentation and the v3 guides (M0).

Step libraries generated by jPipe 2.5.0 still target v3
([#140](https://github.com/jpipe-mcscert/jpipe-runner/issues/140)).
