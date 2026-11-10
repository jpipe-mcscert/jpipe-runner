---
status: accepted
date: 2026-11-10
decision-makers: Sébastien Mosser
---

# ADR-0012: The GitHub Action leaves for jpipe-ci-actions, and runs v4 only

## Context and Problem Statement

Until v4, the GitHub Action lived at this repository's root: `action.yml` and four
scripts under `script/action/`, used as `jpipe-mcscert/jpipe-runner@v3.x`. It drove
jpipe-runner 3, and was coupled to it in three ways:

- **Its inputs were v3's options**: `variable`, `config-file`, a `diagram` pattern and a
  `format`. v4 has none of them (ADR-0008, ADR-0023).
- **Its pull request comment was cut out of the console output**: `build_comment.sh`
  removed v3's ASCII banners with `tail -n +10` and a `sed` on the banner's art, so any
  change to them broke the comment silently (#132). v4 has no banners; programs read its
  JSON report (ADR-0011).
- **Its releases were the runner's**: a fix to the action needed a runner release, and the
  runner's tags carried an `action.yml` that installed an older runner by default.

The plan, made before the rewrite, was to move the action as it was, pinned to runner 3
(#130, MB0), then rebuild it on the JSON report (#132, MB1), in a repository of its own,
`jpipe-runner-action`. By the time MB0 started, v4 was complete, and the
`jpipe-ci-actions` repository existed, with a GitHub Action and a GitLab CI/CD component
in one repository (its ADR-0001).

## Decision Drivers

- The action must keep working for v3 users until they move to v4.
- A release of the action must not wait for a release of the runner, nor the reverse.
- The action must not depend on the runner's text output, whose layout may change.
- No work on an action that is rewritten weeks later.

## Considered Options

1. Keep the action at this repository's root, rebuilt for v4.
2. Move the v3 action as it is, pinned to runner 3 (#130), then rebuild it for v4 (#132).
3. Build the action for v4 directly, in `jpipe-ci-actions`, and delete it here.

## Decision Outcome

Chosen option: **3, build the action for v4 directly, in `jpipe-ci-actions`**, because v3
users lose nothing by it and option 2's first release would be thrown away.

- **The action lives in [`jpipe-ci-actions`](https://github.com/jpipe-mcscert/jpipe-ci-actions)**,
  beside its GitLab counterpart, and is released there, with its own version numbers.
  Its ADR-0002 records how it is built: it runs jpipe-runner 4 only, reads its JSON
  report, and names its inputs in kebab-case.
- **`action.yml` and `script/action/` are deleted from this repository, without a
  forwarding shim.** `uses: jpipe-mcscert/jpipe-runner@v3.6.0`, or any v3 tag, keeps
  working, since a tag is immutable: v3 users are not broken, and move when they port
  their step libraries to v4. `uses: jpipe-mcscert/jpipe-runner@main` stops working.
- **MB1 is folded into MB0**: there is no release of the action pinned to runner 3.

### Consequences

- Good, because the action and the runner are released separately, and the action
  depends only on the runner's command line and its JSON report, both documented and
  tested here.
- Good, because a v3 user changes the action and the step libraries at once, with one
  migration guide (`docs/migration-v3-v4.md`).
- Bad, because a change to the JSON report's schema, or to the exit codes, now reaches a
  program in another repository: the report's versioning (ADR-0011) is what protects it.
- Neutral: the `jpipe-runner-diagrams` branch of this repository, where the v3 action's
  tests committed their diagrams, is left in place; CI ignores it.

### Confirmation

`git ls-files action.yml script/action` comes back empty; the migration guide's
*The GitHub Action* section names `jpipe-mcscert/jpipe-ci-actions`.

## Pros and Cons of the Options

### 1. Keep the action at the root, rebuilt for v4

- Good, because nothing moves.
- Bad, because the action's releases stay tied to the runner's, and GitLab users get
  nothing.

### 2. Move the v3 action as it is, then rebuild it

- Good, because it is what #130 and #132 planned.
- Bad, because its first release, for runner 3, is replaced weeks later, and v3 users
  have the runner's own tags already.

### 3. Build the action for v4 directly, in `jpipe-ci-actions`

- Good, because there is one action to build, on the runner as it will be released.
- Bad, because until 4.0.0 is on PyPI, the action installs the runner from its
  repository.

## More Information

Issues #130, #131 and #132; `jpipe-ci-actions`' ADR-0001 (one repository, two front ends)
and ADR-0002 (runner 4, GitHub first); ADR-0011 (the JSON report is the contract).
