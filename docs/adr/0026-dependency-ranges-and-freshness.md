---
status: accepted
date: 2026-11-10
decision-makers: Sébastien Mosser
---

# ADR-0026: Runtime dependencies are tested ranges, and the lock file is kept fresh

## Context and Problem Statement

jpipe-runner 4.0.0 declares two runtime dependencies in `pyproject.toml`:
`networkx = "3.5"`, an exact pin, and `jsonschema = ">=4.0"`. The pin came in with the
v3.0.0 release commit, and no record says why. Three facts, checked after 4.0.0 was
released, show that it pins nothing anyone tests:

- **The Ubuntu packages ignore it.** `debian/control` depends on an unversioned
  `python3-networkx`, and the published 3.6.0 `.deb` says the same, so the PPA runs on
  the distribution's networkx: 2.8.8 on noble, 3.2.1 on resolute, 3.4.2 on stonking. Its
  jsonschema is 4.10.3 on noble. CI only ever ran on networkx 3.5. The full test suite
  does pass on networkx 2.8.8 and jsonschema 4.10.3 (1,360 tests, checked by hand), but
  nothing keeps it so.
- **pip users pay for it.** The runner is installed in the project's own environment,
  beside the packages its steps import (`docs/cli.md`). An exact pin makes any other
  package that needs another networkx uninstallable beside it.
- **CI ignores the lock file.** The setup action runs `poetry lock` before
  `poetry install`, so every run resolves the dependencies afresh: `poetry.lock` records
  nothing that CI checks. Nothing proposes updates either.

The other jPipe projects have decided how they keep dependencies: the compiler updates
every dependency to its latest stable release before each release, and treats a major
as deliberate work (jpipe-compiler ADR-0007); the VS Code extension installs exactly
what its lock file says in CI, takes weekly grouped updates from Dependabot with majors
apart, and holds a pin only with its reason written down (jpipe-vscode ADR-VSC-0013).
The runner differs from both in one way: it is a library, installed into environments it
does not control, so what it publishes is a constraint on someone else's resolver.

## Decision Drivers

- What the runner declares must be what it is tested on, on every channel it ships to.
- A user's environment must not be blocked by a pin the runner does not need.
- A major version of a dependency is deliberate work, as in the other jPipe projects.
- CI must test what the lock file records, and updates must arrive without someone
  remembering to look.

## Considered Options

1. Keep the exact pin, and declare it in `debian/control` too.
2. A floor only (`>=`), as Python packaging advice usually recommends for libraries.
3. A tested floor and a cap below the next major, a lock file CI honours, and Dependabot.

## Decision Outcome

Chosen option: **3, a tested floor and a cap below the next major**, because it is the
only one that is true on every channel and keeps majors deliberate.

- **Each runtime dependency is a range, `>=floor,<cap`.** The floor is the oldest
  version a supported channel installs: today Ubuntu noble's, `networkx >=2.8.8` and
  `jsonschema >=4.10.3`. The cap is below the next major not yet supported:
  `networkx <4`, `jsonschema <5`. A floor rises when a channel stops shipping the version,
  or when the code needs something newer; a cap rises on a branch that takes the major.
- **`debian/control` declares the same floors**, so that the Ubuntu package states what it
  needs instead of taking any version.
- **CI tests both ends.** The `test` job installs exactly what `poetry.lock` records:
  the setup action no longer runs `poetry lock`, and `poetry install` fails when the lock
  file is out of date. A `test-floor` job installs every runtime dependency at its floor,
  on Python 3.12 as noble does, and runs the whole suite.
- **No exact pin without a reason written here.** There is none today.
- **Dependabot keeps the lock file fresh**, weekly, as in jpipe-vscode ADR-VSC-0013: one
  grouped pull request for Python updates, one for GitHub Actions. It updates the lock
  file only (`versioning-strategy: lockfile-only`), so it never moves a floor or a cap: a
  major arrives on a branch, by hand. Before each release, `poetry show --outdated` lists
  what the caps hold back.

### Consequences

- Good, because the Ubuntu packages run on versions CI tests, and pip users can install
  the runner beside any networkx 2.8.8 to 3.x.
- Good, because a dependency update is a pull request that passes CI and the quality
  gate, like any change.
- Bad, because CI runs one more job, and a floor can hide behind a test that only the
  latest version exercises: the floor job is what catches it.
- Bad, because a networkx 4 cannot be installed beside the runner until a release lifts
  the cap.
- Neutral: Dependabot's pull requests need `SONAR_TOKEN` in Dependabot's own secret store
  to pass the SonarCloud gate (ADR-0004), as jpipe-vscode ADR-VSC-0013 found.

### Confirmation

`tests/unit/test_dependency_policy.py` fails when a runtime dependency has no floor or no
cap, when `debian/control` does not declare the same floors, or when a pin is exact. The
`test-floor` job runs the suite on the floors.

## Pros and Cons of the Options

### 1. Keep the exact pin

- Good, because the version tested is the version installed, on pip.
- Bad, because the Ubuntu series ship none of 3.5, so declaring it in `debian/control`
  makes the package uninstallable on all three.
- Bad, because it blocks every user environment that needs another networkx.

### 2. A floor only

- Good, because it never blocks a user's resolver.
- Bad, because a breaking major reaches users before the runner is tested on it, which
  the other jPipe projects treat as deliberate work.

### 3. A tested floor and a cap below the next major

- Good, because both ends of the range are tested, and a major is a decision.
- Bad, because the cap must be lifted by a release when the next major comes.

## More Information

jpipe-compiler ADR-0007 (dependency freshness), jpipe-vscode ADR-VSC-0013 (dependency
freshness, and a lock file CI honours). ADR-0004 (the quality gate).
