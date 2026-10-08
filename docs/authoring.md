# Writing a step library

A step library is the Python code behind a justification: one function per element whose
claim is checked by running something. This page is the reference for writing one. For a
walk through a complete example, see [`end-to-end.md`](end-to-end.md).

Everything a step library needs is imported from the package itself:

```python
from jpipe_runner import Fail, Outcome, Pass, Skip, conclusion, evidence, strategy, sub_conclusion
```

Nothing else in `jpipe_runner` is meant for step libraries.

## Declaring a step

A step is a function decorated with the kind of the element it implements. The decorator
takes the element's ids as positional arguments, and as keyword arguments the variables
the step consumes and produces, and for evidence the artifacts it observes.

| Decorator | Signature | |
|---|---|---|
| `@evidence` | `(*ids, observes={}, produces=())` | no `consumes`: evidence observes the world |
| `@strategy` | `(*ids, consumes=(), produces=())` | |
| `@sub_conclusion` | `(*ids, consumes=(), produces=())` | optional |
| `@conclusion` | `(*ids, consumes=())` | no `produces`: a conclusion is terminal; optional |

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

- **Evidence and strategies must be implemented.** Each one in the model needs a step;
  validation reports a missing one (`JP005`).
- **Evidence observes artifacts** (see [Observing artifacts](#observing-artifacts)) **and
  reports what it observed**, as values that another step consumes, so that the strategy
  above it judges the facts and not only a verdict. An evidence that observes nothing
  (`JP018`), or whose values no step consumes (`JP012`), is an error.
- **Conclusions and sub-conclusions are optional.** An unbound one takes its status from
  what supports it. Bind one only to check something more about the claim itself; when
  bound, it runs like any other step.
- **A step's parameters are the variables it consumes**, or for evidence the artifacts it
  observes, which the runner passes by name. A parameter with a default value, or
  `**kwargs`, is allowed in addition.
- **`produces` and `consumes` are lists of names**, each a Python identifier, each given
  once. A variable is produced by one step and may be consumed by several.
- **The decorator returns the function unchanged.** A step is a plain function, and can be
  called directly, in a unit test for instance:

```python
assert all_release_gates_pass(tests_pass=False) == Fail("a release gate did not pass")
```

A decorator stacked *above* a step decorator keeps working if it uses `functools.wraps`:
the runner then calls the wrapper.

### Mistakes caught when the library is imported

A declaration that cannot be right raises a `TypeError` when the module is imported, before
any model is read:

| Mistake | Message |
|---|---|
| no id | `@evidence() needs the id of at least one element: @evidence("id")` |
| `@evidence` without parentheses | `@evidence takes the ids of the elements it implements: @evidence("id")` |
| a string instead of a list | `@evidence(produces=...) takes a list of names: produces=['tests_pass']` |
| a name that is not an identifier | `@evidence(produces=...) takes variable names that are Python identifiers, not 'tests-pass'` |
| a parameter that is not consumed | `@strategy gates: its parameters ['changelog_ok'] are not consumed, so nothing would pass them. …` |
| an observed artifact that is not a parameter | `@evidence the_changelog_is_up_to_date: it observes ['changelog'] but has no parameter for them. …` |
| a list instead of a mapping | `@evidence(observes=...) maps each parameter to the path it receives: observes={'changelog': 'CHANGELOG.md'}` |
| an absolute path | `@evidence(observes=...) takes paths relative to the run's working directory, so that the library works on every machine, not '/home/me/CHANGELOG.md'` |
| a directory | `@evidence(observes=...) takes files, and 'src/' names a directory. Observe the files it holds, with a glob such as 'src/**/*'.` |
| two step decorators on one function | `f is already declared as evidence ('release:e1',): one function is one step` |

Whether the ids designate elements of the model, and whether the data flows (every consumed
variable produced by a step that supports its consumer), depends on the model. Those are
checked against it before anything runs: see [Validation](#validation-checking-the-library-against-the-model).

## Observing artifacts

Evidence is where the argument touches the world: a test report, a changelog, a source
tree. `observes` declares what an evidence reads, as a mapping from each of the function's
parameters to a path, and the runner passes the artifact to that parameter
([ADR-0018](adr/0018-evidence-declares-observed-artifacts.md)).

```python
from pathlib import Path

from jpipe_runner import Outcome, Pass, evidence


@evidence(
    "release:e3",
    observes={"reports": "build/reports/*.xml", "sources": "src/**/*.py"},
    produces=["report_count", "source_count"],
)
def every_module_has_a_report(reports: list[Path], sources: list[Path]) -> Outcome:
    return Pass(report_count=len(reports), source_count=len(sources))
```

| Path | Names | The parameter receives |
|---|---|---|
| `"CHANGELOG.md"` | a file | a `Path` |
| `"build/reports/*.xml"` | the files a glob matches (`**` matches any depth) | their sorted `list[Path]` |

- **An evidence observes files.** A directory, written `"src/"`, is refused when the
  library is imported: observe the files it holds, with a glob such as `"src/**/*"`
  ([ADR-0019](adr/0019-evidence-observes-files.md)).
- **Paths are relative** to the directory the runner runs in. An absolute path is refused
  when the library is imported: the library must work on every machine.
- **An observed artifact is never optional.** When the steps run, an artifact that is not
  there, or a glob that matches nothing, fails the evidence (M4). A check that a file is
  *absent* does not declare it.
- **Every evidence observes something.** One that observes nothing checks nothing in the
  world, and is an error (`JP018`): a placeholder that returns `Pass()` is fake evidence.
- **Only evidence observes.** A strategy that needs a file has an evidence inside it:
  split it into an evidence that reads the file, and the strategy that judges what it
  produced.
- **The runner records what was observed**, and the report lists it, so that a CI
  pipeline can archive the artifacts with the verdict (M4, M5).

Since the runner passes the artifact, a test passes its own:

```python
import tempfile

with tempfile.TemporaryDirectory() as directory:
    log = Path(directory) / "tests.log"
    log.write_text("42 passed\n", encoding="utf-8")
    assert the_test_suite_passes(log) == Pass(tests_pass=True)
```

## Returning an outcome

A step returns one of three outcomes:

| Outcome | Meaning |
|---|---|
| `Pass(...)` | The check holds. It carries the values the step produces. |
| `Fail(reason)` | The check does not hold, for `reason`. |
| `Skip(reason="")` | The step cannot judge, for `reason`: what it supports is not judged either. |

`Pass` takes the produced values as a mapping, as keywords, or both:

```python
from jpipe_runner import Pass

assert Pass({"coverage": 92.0}) == Pass(coverage=92.0)
assert Pass({"coverage": 92.0}, tests_pass=True).values == {"coverage": 92.0, "tests_pass": True}
```

Outcomes are immutable, and compare by value.

### Why not `True` and `False`

v3 steps returned a boolean and produced values by calling an injected `produce`
parameter. The verdict and the values travelled separately, there was no way to say "I
cannot judge", and a failure carried no reason. An outcome carries all three in one value
([ADR-0005](adr/0005-outcomes-as-return-values.md)).

A step that still returns a boolean, or nothing, is reported with `JP017`, and told what to
return instead:

```
JP017 error [release:e1]: the step returned True, which is not an outcome
  fix: Return Pass() instead of True.
```

A step that raises an exception will fail, with the exception in the report (M4).

## Binding: how an id designates an element

The ids a step is given are matched against the ids of the model's elements, as the jPipe
compiler exports them (`release:e1` for `e1` in `justification release`). An id designates
an element by the first of these rules that matches
([ADR-0007](adr/0007-binding-resolution.md)):

1. **Exact:** it is the element's id, or one of its aliases.
2. **Qualified:** it is `<justification name>:<id>`, and `<id>` is exact.
3. **Suffix:** it is a strictly shorter tail of the element's id or of an alias, cut at
   `:`.

For an element `rigor:r17:e_metric`:

| Id in the step | Designates it? | |
|---|---|---|
| `rigor:r17:e_metric` | yes | exact |
| `r17:e_metric`, `e_metric` | yes | a tail, cut at `:` |
| `metric` | no | part of a segment |
| `r17` | no | not a tail |

An exact match always wins: if another element's id is exactly `e_metric`, then
`e_metric` designates that one. A tail shared by two elements designates neither, and is
reported (`JP006`): use a longer id.

### One element, one function

Binding is one to one, and every problem is reported at once:

| Code | Problem |
|---|---|
| `JP015` | an id designates no element, so the function would never run |
| `JP006` | an id designates several elements |
| `JP007` | an element is implemented by several functions, or a function's ids designate several elements |

A step may be given **several ids for the same element**. This is what composition
produces: when models are merged, an element keeps the ids it had in each source, as
aliases, and the compiler writes all of them on its step.

```python
from pathlib import Path

from jpipe_runner import Outcome, Pass, evidence


@evidence(
    "rigor:r17:e_metric",
    "rigor:r18:e",
    observes={"metrics": "reports/metrics.csv"},
    produces=["metrics_reported"],
)
def report_metrics(metrics: Path) -> Outcome:
    return Pass(metrics_reported=metrics.stat().st_size > 0)
```

A function **cannot implement several elements**. Two elements are two claims, and each
has its own step; when they are checked the same way, share the code, not the step:

```python
from pathlib import Path

from jpipe_runner import Outcome, Pass, evidence


def _line_count(file: Path) -> int:
    return len(file.read_text(encoding="utf-8").splitlines())


@evidence("release:e1", observes={"log": "build/tests.log"}, produces=["test_log_lines"])
def the_test_log_is_written(log: Path) -> Outcome:
    return Pass(test_log_lines=_line_count(log))


@evidence("release:e2", observes={"changelog": "CHANGELOG.md"}, produces=["changelog_lines"])
def the_changelog_is_written(changelog: Path) -> Outcome:
    return Pass(changelog_lines=_line_count(changelog))
```

### When the model is composed

Write a step library against the model you have. If that model is later composed with
others, the library keeps binding:

- **`assemble` prefixes the ids** with the composed model's name: `tested:e` becomes
  `ready:tested:e`. The old id is a tail of the new one.
- **`refine` merges the hook into a sub-conclusion** that keeps the hook's id as an alias.
  An `@evidence("draft:tests")` written against the draft still binds, now to a node that
  is argued in full below it. It runs after that sub-argument, as an independent
  cross-check of the same claim, and validation reports the change of kind as a warning
  (`JP008`), not an error ([ADR-0013](adr/0013-kind-divergence-under-composition.md)).
- The refinement's conclusion is aliased onto the same element. Binding both the hook's id
  and the refinement's conclusion is two functions for one element: `JP007`.

## Validation: checking the library against the model

Before running any step, the runner checks the library against the model, and reports
every problem at once. An error stops the run: no step executes. A warning is reported,
and the run continues. [`rules.md`](rules.md) describes every check; in short:

- every evidence and every strategy has a step (`JP005`), and ids bind one to one
  (`JP006`, `JP007`, `JP015`);
- a step's decorator is its element's kind (`JP016`), unless composition changed the
  element's kind (`JP008`, a warning);
- every consumed variable is produced by one step (`JP009`, `JP010`), which supports its
  consumer, directly or not (`JP014`): a step runs only after its supporters pass, so a
  value from another branch might never exist;
- an evidence produces a value another step consumes (`JP012`); a strategy consumes what
  its supporters produce for other steps (`JP013`, a warning), and a produced value is
  consumed somewhere (`JP011`, a warning).

## Coming from v3

| v3 | v4 |
|---|---|
| `@jpipe(consume=[...], produce=[...])` and `@jpipe_link("id")` | `@evidence("id", produces=[...])`, `@strategy("id", consumes=[...], produces=[...])`, … |
| a `produce` parameter, `produce("x", value)` | `return Pass(x=value)` |
| `return True` / `return False` | `return Pass()` / `return Fail("why")` |
| `@skip(condition, reason)` | `return Skip(reason)`, decided when the step runs |
| `@contribution(...)` | removed |
| `--variable`, `--config-file` | removed: read inputs in a step ([ADR-0008](adr/0008-drop-external-variable-injection.md)) |
| a file opened by path inside the step | `@evidence(..., observes={"name": "path"})`, received as a parameter |
| `from jpipe_runner.framework.decorators… import …` | `from jpipe_runner import …` |

Importing `jpipe_runner.framework` raises an `ImportError` that says this. Step libraries
generated by jPipe 2.5.0 and earlier are written for v3
([#140](https://github.com/jpipe-mcscert/jpipe-runner/issues/140)).
