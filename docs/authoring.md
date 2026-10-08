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
takes the element's ids as positional arguments, and the variables the step consumes and
produces as keyword arguments.

| Decorator | Signature | |
|---|---|---|
| `@evidence` | `(*ids, produces=())` | no `consumes`: evidence observes the world |
| `@strategy` | `(*ids, consumes=(), produces=())` | |
| `@sub_conclusion` | `(*ids, consumes=(), produces=())` | optional |
| `@conclusion` | `(*ids, consumes=())` | no `produces`: a conclusion is terminal; optional |

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

- **Evidence and strategies must be implemented.** Each one in the model needs a step;
  validation reports a missing one (`JP005`, from M3).
- **Conclusions and sub-conclusions are optional.** An unbound one takes its status from
  what supports it. Bind one only to check something more about the claim itself; when
  bound, it runs like any other step.
- **A step's parameters are the variables it consumes**, which the runner passes by name.
  A parameter with a default value, or `**kwargs`, is allowed in addition.
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
| two step decorators on one function | `f is already declared as evidence ('release:e1',): one function is one step` |

Whether the ids designate elements of the model, and whether the data flows (every consumed
variable produced, no cycle), depends on the model. Those are checked against it, as
described below and in [M3](v4-progress.md).

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
from jpipe_runner import Outcome, Pass, evidence


@evidence("rigor:r17:e_metric", "rigor:r18:e", produces=["metrics_reported"])
def report_metrics() -> Outcome:
    return Pass(metrics_reported=True)
```

A function **cannot implement several elements**. Two elements are two claims, and each
has its own step; when they are checked the same way, share the code, not the step:

```python
from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence


def _file_check(path: str) -> Outcome:
    return Pass() if Path(path).is_file() else Fail(f"{path} not found")


@evidence("release:e1")
def the_test_suite_passes() -> Outcome:
    return _file_check("mock/tests.ok")


@evidence("release:e2")
def the_changelog_exists() -> Outcome:
    return _file_check("mock/CHANGELOG.md")
```

### When the model is composed

Write a step library against the model you have. If that model is later composed with
others, the library keeps binding:

- **`assemble` prefixes the ids** with the composed model's name: `tested:e` becomes
  `ready:tested:e`. The old id is a tail of the new one.
- **`refine` merges the hook into a sub-conclusion** that keeps the hook's id as an alias.
  An `@evidence("draft:tests")` written against the draft still binds, now to a node that
  is argued in full below it. It runs after that sub-argument, as an independent
  cross-check of the same claim, and validation will flag the change of kind as a warning
  (`JP008`, M3), not an error.
- The refinement's conclusion is aliased onto the same element. Binding both the hook's id
  and the refinement's conclusion is two functions for one element: `JP007`.

## Coming from v3

| v3 | v4 |
|---|---|
| `@jpipe(consume=[...], produce=[...])` and `@jpipe_link("id")` | `@evidence("id", produces=[...])`, `@strategy("id", consumes=[...], produces=[...])`, … |
| a `produce` parameter, `produce("x", value)` | `return Pass(x=value)` |
| `return True` / `return False` | `return Pass()` / `return Fail("why")` |
| `@skip(condition, reason)` | `return Skip(reason)`, decided when the step runs |
| `@contribution(...)` | removed |
| `--variable`, `--config-file` | removed: read inputs in a step ([ADR-0008](adr/0008-drop-external-variable-injection.md)) |
| `from jpipe_runner.framework.decorators… import …` | `from jpipe_runner import …` |

Importing `jpipe_runner.framework` raises an `ImportError` that says this. Step libraries
generated by jPipe 2.5.0 and earlier are written for v3
([#140](https://github.com/jpipe-mcscert/jpipe-runner/issues/140)).
