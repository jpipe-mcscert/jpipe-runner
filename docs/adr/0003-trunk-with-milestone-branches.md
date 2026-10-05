---
status: accepted
date: 2026-10-05
decision-makers: Sébastien Mosser
---

# A single `main` trunk, one pull request per milestone

## Context and Problem Statement

Up to 3.6.0 the repository followed a git-flow-lite model with three long-lived branches:

- `main` held released code;
- `dev` was the integration branch and the GitHub default;
- `v4` held the from-scratch rewrite (ADR-0002).

A change went feature → `dev` (PR), then `dev` → `main` (PR), then a tag. This produced
many pull requests that added little:

- **Half the pull requests came from the branch model, not from a piece of work.** Between
  2026-07-18 and 2026-10-05 there were 12 PRs for 4 releases (3.5.1–3.6.0). Six of them:
  - `dev` → `main` merges: #97, #99, #100 and #135;
  - a release-prep PR: #134;
  - a hotfix routed straight to `main`, around `dev`: #98.

  Releasing 3.6.0 alone took two PRs, #134 then #135.
- **Reviewed diffs were reviewed again.** #135 (+1074 lines) re-presented #101–#105 and
  #134 verbatim, and #97 did the same for #76–#96. Copilot reviewed them a second time, and each of its comments had to be
  answered.
- **Pull requests gated nothing.** No branch was protected and no check was required. The
  unit-test workflow (`ci.yml`) ran on pushes to `main` and `dev` only, not on pull
  requests and not on `v4`. The rewrite had no CI at all.
- **`dev` and `main` held identical code.** After v3 was frozen at 3.6.0 (no maintenance
  branch, see [`docs/contributing.md`](../contributing.md)), neither branch had a job left.
  The `v3.6.0` tag already preserves that code.
- **`Closes #N` did not work for v4.** GitHub closes an issue only when the referencing
  commit reaches the default branch (`dev`), and v4 commits never would.

The v4 rewrite has about 27 tickets (#107–#133) across 10 milestones (M0–M7, MB0, MB1).
Kept unchanged, the model would have produced about 30 pull requests before 4.0.0.

How should branches and pull requests be organised so that each pull request is worth
reviewing?

## Decision Drivers

- Every pull request is a real review checkpoint, not a transfer between branches.
- CI runs on all work, including work that has not reached a pull request yet.
- Issues close from the commits that resolve them.
- v3 stays reachable, both installed (PyPI, the `v3.6.0` tag) and as source to read.
- Integration stays a human decision. Automated assistants push branches; they never merge,
  push to `main`, or tag.

## Considered Options

1. Keep git-flow-lite: `main`, `dev` and `v4`, with one pull request per ticket.
2. A `main` trunk with direct commits, and pull requests only on demand.
3. A `main` trunk with one milestone branch, and one pull request, per milestone.
4. Keep `v4` as a long-lived branch until 4.0.0, then fold it into `main`.

## Decision Outcome

Chosen option: **3, a `main` trunk with one pull request per milestone.** It removes every
pull request that only moves code between branches, and it keeps a human review point at
each milestone, the unit the v4 plan is already organised around.

- **One long-lived branch, `main`**, which is also the default branch. `dev` and `v4` are
  deleted. `v4` becomes `main` by fast-forward (`main` was already an ancestor of `v4`), so
  no history is rewritten. v3 stays reachable as the `v3.6.0` tag.
- **One branch per milestone**, cut from `main`: `m0-foundation`, `m1-model`, …,
  `m7-docs`, `mb-action`.
  - Each ticket is one or more commits whose message ends in `Closes #N`.
  - The branch is pushed often, and CI runs on every push.
  - When the milestone is complete, the maintainer opens one pull request into `main` and
    merges it with a merge commit, so the per-ticket commits, and the issues they close,
    survive.
- **Other pull requests** are for contributions from people outside the maintainer team,
  or for a one-off change the maintainer wants reviewed. These are squash-merged.
- **Releases are tags on `main`**, which `release.yml` already keys on. The version bump
  and the CHANGELOG entry go in as the last commit of the milestone being released, or as
  a maintainer commit on `main`. A release needs no pull request of its own.

### Consequences

- Good, because the v4 rewrite needs about 10 pull requests instead of about 30, and each
  one is a coherent piece of work.
- Good, because a released change is reviewed once, not once per branch it passes through.
- Good, because CI covers v4 from its first commit.
- Good, because `Closes #N` works, so each issue links to the commits that resolve it.
- Bad, because milestone pull requests are large, and reviewing them takes more effort
  than reviewing a single ticket.
- Bad, because the repository's landing page shows the unfinished v4 README until the
  rewrite reaches M7 (#129), while PyPI still serves 3.6.0.
- Bad, because CI on `m0-foundation` goes red between #107 (deleting `src/` and `tests/`)
  and #108 (the new test tooling). Both are in M0, so `main` never sees it.

### Confirmation

- The remote has `main`, `jpipe-runner-diagrams` (the GitHub Action's image output branch)
  and at most one or two milestone branches.
- The repository's default branch is `main`.
- A merged milestone pull request closes that milestone's issues automatically.

## Pros and Cons of the Options

### 1. Keep git-flow-lite, one pull request per ticket

- Good, because it needs no change.
- Bad, because of every problem listed in the context: the ceremony PRs, repeated reviews,
  no CI on `v4`, and no automatic issue closing.

### 2. Trunk with direct commits, pull requests on demand

- Good, because it has the least overhead.
- Bad, because nothing marks a review point. Either the maintainer reviews every commit on
  `main` after the fact, or nobody does.
- Bad, because it requires automated assistants to push to `main`, which the
  integration-stays-human driver rules out.

### 4. Keep `v4` until 4.0.0

- Good, because the landing page and `main` keep matching the released 3.6.0 until v4 ships.
- Bad, because it keeps two long-lived branches for the whole rewrite. `main` would be a
  frozen copy of a tag, and the final `v4` → `main` pull request would be one more
  ceremony PR.

## More Information

- [`docs/contributing.md`](../contributing.md) describes the day-to-day workflow.
- GitHub Action users are unaffected. The Action is pinned by tag (`@v3.6.0`), and
  [`docs/ACTION.md`](../ACTION.md) already advised against `@main`.
