---
status: accepted
date: 2026-10-08
decision-makers: Sébastien Mosser
---

# ADR-0010: Diagnostics as data, rules as objects, real severity levels

## Context and Problem Statement

Before it runs anything, the runner checks the step library against the model. Is every
evidence implemented? Does every consumed variable have a producer? Does each function's kind
agree with its element's? v3 did this with eight validator classes
(`git show v3.6.0:src/jpipe_runner/framework/validators/`). Each returned two lists of
pre-formatted strings, errors and warnings. Three problems came with that design:

- **The text was the data.** About 60% of the validators' lines were hand-formatted,
  multi-line messages. Nothing identified a problem except its wording, so neither a test
  nor a report could say which problem it was. One message on the most common failure path
  (`missing_variable.py`) lacked its `f` prefix and showed users a literal `{var}`.
- **Severity was not real.** `engine.py` set `all_passed = False` on errors *or* warnings,
  and the log buffer counted anything at `WARNING` or above as an error. Overriding a
  configuration key with `-v`, which is what `-v` was for, made a clean dry run exit 1,
  under a full-screen `ERROR LOG` banner, for a warning.
- **Nothing said what the checks were.** The only list of what v3 validated was the code
  of eight classes. Their documentation, where it existed, had drifted from them.

M1 and M2 made the model and binding report `Diagnostic`s, each with a code, a severity, a
message, the element it is about and a fix. M3 (#118, #119) builds validation on top of
them. How should a validation check be written, run and reported, and what should its
severity mean?

## Decision Drivers

- **A code identifies a problem.** Tests, reports and users rely on `JPnnn`. The message
  is written for humans and may be reworded.
- **Severity means something.** An error stops the run, and a warning does not.
- **Every problem is reported at once.** One problem never hides another.
- **A human can audit every rule.** An assurance tool's checks are part of the argument it
  supports. A reviewer must be able to read what each rule checks, why, and what it
  reports, in one place, and to trust that this is what the code does.
- **The reference cannot drift.** The documentation of the rules comes from the rules.
- **No configuration weakens a check.** Two runs of one library against one model judge it
  the same way.

## Considered Options

1. v3's design: validator classes returning lists of formatted strings.
2. Rules as classes: each one a `Rule` whose code, severity and summary are class
   attributes and whose docstring explains it, run by a `RuleSet` that collects
   `Diagnostic`s.
3. Rules as functions registered by a decorator that takes the code, severity and summary.

## Decision Outcome

Chosen option: **2, rules as classes**, because a class carries its metadata, its
explanation and its check together, where a reviewer reads them as one unit, and a
`RuleSet` can refuse a rule that lacks any of them. Option 3 carries the same data, but
its explanation would be the docstring of a function whose name is not the rule's, and its
metadata a decorator's arguments, which are harder to read and to generate a page from.

`jpipe_runner.validation` holds the framework, and `jpipe_runner.rules` holds every rule,
in one module:

- **`Rule`** declares `code`, `severity` and `summary` as class attributes. Its docstring
  says what it checks, why it matters, and how to fix what it reports. `check(ctx)` yields
  diagnostics, built with `self.diagnostic(...)`, which fills in the rule's code and
  severity.
- **`ValidationContext`** is what a rule reads: the `Justification`, the `StepRegistry`,
  and the `BindingTable` of one to the other. It also indexes the bound steps that produce
  and consume each variable. Only bound steps count: a step that binds no element never
  runs, so nothing it declares is ever produced.
- **`RuleSet`** runs its rules in code order. It collects every diagnostic in a
  **`ValidationReport`**, which `passed` when none is an error. It refuses a rule without a
  `JPnnn` code, a severity, a summary or a docstring, and two rules with one code. A rule
  that reports another rule's code is a bug, and raises.

**Severity is real.** An `ERROR` blocks execution. A `WARNING` is reported, and the run
continues and can succeed. An `INFO` is reported only. A **strict** run
(`run(ctx, strict=True)`, `--strict` from M6) reports every warning as an error. A warning
never changes the exit status of a run that is not strict.

**No rule can be disabled.** Disabling an error would let a run start that cannot work.
Disabling a warning would hide, from the readers of an assurance case, something it should
show. A noisy rule is fixed in the library it reports on, or its severity is changed by a
decision recorded here, for everyone.

**The model's own soundness is not a rule.** A `Justification` that exists is valid: the
loader and the constructor refuse what the model alone shows to be unrunnable, with every
problem at once (`JP001` to `JP003`, M1). This includes **a cycle in the relations
(`JP004`)**, which #119 had listed as a rule. The compiler never emits a cycle, so a
cyclic JSON is malformed input. Refusing it at load time means no rule, and no later stage,
ever has to consider one. This amends [ADR-0016](0016-hide-the-graph-inside-justification.md):

- `Justification.cycle()` is no longer one of the model's queries.
- `topological_order()` no longer raises.
- `upstream(id)`, every element that supports an element directly or not, is added for
  the rules.

### Consequences

- Good, because a test asserts a code and a severity, never a message substring, and a
  message can be reworded without breaking anything.
- Good, because the reference of the rules, `docs/rules.md`, is generated from their
  classes, and a test fails when it differs (#128).
- Good, because one module holds every rule, each a short class whose docstring is the
  rule's specification, so a reviewer audits all of them in one reading.
- Good, because a warning, such as an unconsumed output, no longer fails a run.
- Bad, because a library that triggers a warning keeps reporting it until it is fixed:
  there is no switch to silence it.
- Bad, because a model with a cycle is refused before its step library is even bound, so
  binding problems in that library surface only once the cycle is fixed.

### Confirmation

- `tests/unit/test_validation.py` pins the framework: code order, every diagnostic
  collected, warnings that do not block, strict promotion, and the refusal of a rule that
  cannot be audited.
- Each rule has its own table-driven test module under `tests/unit/validation/rules/`,
  asserting codes, severities and elements, never messages (`tests/README.md`).
- `tests/unit/test_rules_doc.py` fails when `docs/rules.md` is not what the rules generate.
- `tests/unit/test_model.py` checks that a cycle is refused with `JP004`.

## Pros and Cons of the Options

### 1. Validator classes returning formatted strings

- Good, because it already existed.
- Bad, because a problem is identified by its wording, which tests then pin.
- Bad, because severity is a list a validator appends to, and v3's engine ignored it.

### 2. Rules as classes

- Good, because metadata, explanation and check are one unit, refused when incomplete.
- Good, because a page of every rule can be generated from them.
- Neutral, because each rule is a small class rather than a function.

### 3. Rules as decorated functions

- Good, because a rule is a few lines shorter.
- Bad, because the rule's name, code and explanation are spread across a decorator call, a
  function name and a docstring.

## More Information

- #118 (this decision), #119 (the rules), #128 (`docs/rules.md`).
- [ADR-0016](0016-hide-the-graph-inside-justification.md), amended by this record.
