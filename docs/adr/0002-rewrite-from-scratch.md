---
status: accepted
date: 2026-10-05
decision-makers: Sébastien Mosser
---

# ADR-0002: Rewrite from scratch on a branch rather than port v3

## Context and Problem Statement

v3 (frozen at 3.6.0) is 3,338 lines of Python in `src/` and 5,428 lines of tests. It was
built in two eras. Up to 1.0.0 the runner parsed `.jd` itself. From 2.0.0 it consumed
compiler JSON (ADR-0001). The second era was built on top of the first, and its interface
was never redesigned.

Reviewing v3 for the v4 plan (#106–#133) found that the defects are in the structure, not
scattered bugs:

- **State.** A module-level `RuntimeContext` singleton holds every variable in one flat,
  process-wide namespace. `None` cannot be told apart from "unset", nothing is reset
  between runs, and decorators must run before `load_config` (#117).
- **Severity is not real.** Any warning fails the run, so overriding a config key with
  `-v` turns a clean dry run into exit 1 (#118).
- **Failures are swallowed.** An unparseable justification becomes an empty graph that
  "succeeds" (#112). A decorator id that matches nothing is skipped without a word (#115).
  Most load-time exceptions escape as bare tracebacks (#120).
- **The CLI does less than it claims.** `--diagram` is parsed and never read. `-V` produces
  byte-identical output, because no handler can receive INFO records. Every error exits
  with code 1 (#124).
- **The tests assert little.** The `unit` and `e2e` markers are declared but applied to no
  test, so `pytest -m unit` selects nothing (#108). The e2e tests mostly assert a return
  code (#133).
- **The authoring API.** The `produce` callable, `@jpipe` + `@jpipe_link`, and an AST pass
  policing `consume` get replaced by return values and one decorator per kind (#113, #114).

Almost every module is touched by at least one of these. The question is how to get to a
v4 without these problems.

## Decision Drivers

- The authoring API, the state model, the diagnostics and the CLI all change at once, so
  hardly any v3 interface survives as is.
- v3 users need a stable, installable release while v4 is built.
- The reasoning behind each v4 choice must be recorded (unlike ADR-0001).
- The packaging and release plumbing (Debian, Homebrew, PyPI, the release workflow) works
  and was hard to get right. It must not be lost.

## Considered Options

1. Refactor v3 incrementally, keeping it releasable at each step.
2. Port v3 module by module into a new layout, keeping its code where it fits.
3. Rewrite from scratch on a separate line of development, against the v4 issues.

## Decision Outcome

Chosen option: **3, a rewrite from scratch.** v3's tests pin the behaviour v4 removes, so
an incremental refactor would spend most of its effort keeping intermediate states working
that nobody wants. A port carries over the structure the review found wanting.

- v3 freezes at **3.6.0**, with no maintenance branch, back-ports or compatibility matrix.
  It stays installable from PyPI and from the `v3.6.0` tag.
- The v4 work starts by deleting `src/` and `tests/` (#107). The v3 code is consulted with
  `git show v3.6.0:<path>`, never copied back into the tree
  ([`docs/contributing.md`](../contributing.md)).
- The rewrite is driven by the v4 issues (#107–#133), grouped in milestones M0–M7, MB0 and
  MB1. Each significant choice gets an ADR when its issue lands.
- **Ported, not rewritten:** v3 logic that is well specified and correct. The main case is
  the binding resolution rule (#115).
- **Carried over untouched:** packaging and release plumbing: `debian/`, `Formula/`,
  `setup.py`, `MANIFEST.in`, `bin/`, `pyproject.toml`, the workflows.
- **Input format unchanged:** the compiler's JSON (ADR-0001).

The rewrite was first developed on a long-lived `v4` branch. ADR-0014 later made that
branch `main`, with one branch per milestone.

### Consequences

- Good, because the v4 structure (registry and value store, rules as objects, outcomes as
  return values) can be designed for the job rather than worked around v3.
- Good, because v3 users have a fixed reference point (3.6.0) and v4 can break things
  without a deprecation path.
- Good, because every ticket names the v3 defect it fixes, so the rewrite has a checklist.
- Bad, because nothing on the v4 line is releasable until M6 (the CLI) lands.
- Bad, because 4.0.0 is a breaking change for every v3 user. `--variable`,
  `--config-file`, `@jpipe` and `produce` disappear, and a migration guide is needed (#129).
- Bad, because v3 behaviour that turns out to be right has to be rediscovered from the tag
  and ported deliberately.

### Confirmation

- `src/` contains no file copied from `v3.6.0`, except code a ticket explicitly ports (#115).
- No `release/3.x` branch exists and no commit after `v3.6.0` changes v3 code.

## Pros and Cons of the Options

### 1. Incremental refactor

- Good, because the project stays releasable throughout.
- Bad, because the singleton, the authoring API and the diagnostics are interdependent, so
  each step has to keep the old and new forms working together.
- Bad, because v3's own tests would have to be kept passing, and they encode the
  behaviour being removed.

### 2. Port module by module

- Good, because it reuses code that already runs.
- Bad, because the v3 module boundaries (one `engine.py` doing loading, validation,
  execution and export) are part of the problem.
- Bad, because ported code brings its implicit behaviour with it, undocumented.

## More Information

- [`docs/contributing.md`](../contributing.md) explains how to consult the v3 code.
- ADR-0001 covers the input format. ADR-0014 covers the branching that replaced the `v4`
  branch.
