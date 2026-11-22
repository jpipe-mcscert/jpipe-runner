---
status: accepted
date: 2026-11-22
decision-makers: Sébastien Mosser
---

# ADR-0037: A step reads what it is passed, as its bytecode shows

## Context and Problem Statement

A step declares what it consumes and, for an evidence, what it observes. The argument is
read from those declarations: a strategy that consumes `coverage` judges from the coverage,
`StrategyIgnoresUpstreamOutput` (`JP013`) is satisfied as soon as it declares the variable,
and `jpipe-runner impact` reports the step as affected when the coverage changes
([ADR-0025](0025-impact-and-staleness.md)).

v3 checked that a step read what it consumed: `ConsumedVariableChecker` parsed the
function's source and refused a consumed variable that the body never named.
[ADR-0005](0005-outcomes-as-return-values.md) dropped that pass, because the source of a
function typed at a prompt, made by a decorator factory or compiled is not available, and
because a name anywhere in the body counted as a read. v4 kept a signature check instead
(`steps._check_signature`): each input has a parameter, and each required parameter is an
input. That guarantees that a value **reaches** the function, not that the function **looks
at it**:

```python
@strategy("s", consumes=["coverage", "threshold"])
def ignores(coverage: float, threshold: float) -> Outcome:
    return Pass()  # judges from neither
```

The argument then claims a dependency the code does not have, and nothing says so (#190).
Should the runner check again that a step reads its inputs, and how?

## Decision Drivers

- **What the argument claims is what the code does**, or the difference is reported.
- **Every step can be checked**, whatever made its function: a module, a prompt, `exec`.
- **No false error.** What a step does with a value cannot be decided; a check that refuses
  a library must be certain.

## Considered Options

1. Leave it: the signature check is enough.
2. Parse the source again, as v3 did.
3. Read the bytecode, and warn.

## Decision Outcome

Chosen option: **3, read the bytecode, and warn**, as `JP027` `UnreadInput`.

- **A parameter is read** when an instruction of the function's code loads it, or when it is
  a cell variable, which a nested function reads, or when the function calls `locals()` or
  `vars()`, which hand every variable on. The instructions on a variable are the ones the
  running Python lists (`dis.haslocal`, `dis.hasfree`), and their names say what each does
  to each variable it names: `LOAD_FAST_LOAD_FAST` loads two, `STORE_FAST_LOAD_FAST` stores
  its first and loads its second. An instruction whose name does not say, as a later Python
  may add, counts as a read: a missed warning is the safe way to be wrong.
  `LOAD_FAST_AND_CLEAR`, which saves a variable a comprehension is about to reuse, is not a
  read. A global of the same name is not the parameter. Passing the value to a helper
  counts, whatever the helper does with it.
- **The function checked is the one declared**, under its `functools.wraps` wrappers, as
  `inspect.signature`, and so the signature check, sees it: unwrapping stops at a function
  that declares its own `__signature__`.
- **It is a warning, on a bound step.** The check is a heuristic, so it reports rather than
  refuses, among the rules, where `--strict` makes it an error for those who want it. A step
  that binds no element never runs, and is not checked.
- **What a step takes only through `**kwargs`** cannot be checked by name. It gets the same
  warning, with its own message, rather than passing silently: naming the input as a
  parameter settles it.
- **Evidence is covered as well as the other kinds**: an observed artifact never read is
  the same gap.

This amends ADR-0005's consequence that no pass looks at the function's body: the body is
read again, from its bytecode, which needs no source, and only to warn.

### Consequences

- Good, because a strategy that judges without looking at what it consumes, or an evidence
  that never opens what it observes, is reported, and `impact` stops being wrong about it
  silently.
- Good, because steps without a source, typed at a prompt or built by `exec`, are checked.
- Good, because the compiler's generated skeletons are untouched: `PythonExporter` declares
  `consumes=[]` and `observes={}`, so nothing is passed to them.
- Bad, because a parameter that a comprehension's variable of the same name shadows passes
  for read on Python 3.12 and later, where the comprehension is inlined and its variable is
  the parameter's slot, but not on 3.11: the warning then depends on the interpreter. Such a
  function shadows its own parameter, which linters already report.
- Bad, because the instructions are CPython's, and change between versions. A new version
  cannot cause a false warning, but its new loads may need decoding for the check to keep
  finding unread inputs. CI runs the tests on 3.11 and 3.12; the paired and borrowed loads
  of 3.13 and 3.14 were checked by running the tests on those versions.
- Neutral, because existing libraries may see new warnings; a run is not stopped by them
  unless it is strict.

### Confirmation

- `tests/unit/test_steps.py` checks what counts as a read: directly, two at once, in a
  comprehension, in a nested function, through a helper or `locals()`, in a function built
  by `exec`, under a wrapper above or below the decorator, and an instruction the check does
  not know; a global of the same name does not count.
- `tests/unit/validation/rules/test_unread_input.py` checks the rule and its messages.

## Pros and Cons of the Options

### 1. The signature check is enough

- Good, because nothing new can go wrong.
- Bad, because a step can ignore every input, and the argument still claims it uses them.

### 2. Parse the source

- Good, because v3 did it.
- Bad, because it fails without a source, and counts a global or an attribute of the same
  name as a read.

### 3. Read the bytecode, and warn

- Good, because it needs no source and knows a local from a global.
- Bad, because it depends on CPython's instructions.

## More Information

- #190 (this decision), [ADR-0005](0005-outcomes-as-return-values.md) (amended),
  [ADR-0010](0010-diagnostics-as-data-rules-as-objects.md) (rules and warnings).
