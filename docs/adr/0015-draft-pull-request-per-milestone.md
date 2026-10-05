---
status: accepted
date: 2026-10-05
decision-makers: Sébastien Mosser
---

# ADR-0015: Open each milestone's pull request as a draft when the milestone starts

This record amends [ADR-0014](0014-trunk-with-milestone-branches.md). It changes when the
milestone pull request is opened, and nothing else: there is still one pull request per
milestone, merged into `main` with a merge commit.

## Context and Problem Statement

ADR-0014 has the pull request opened "when the milestone is complete". Until then, a
milestone branch gets only `ci.yml` (lint, types, tests) on each push.

ADR-0004 then made SonarCloud the quality gate. Its first run, from `m0-foundation`,
authenticated and uploaded its report, and was then refused: the `jpipe-mcscert`
organisation's plan analyses the main branch and pull requests, and no other branch
("Organization is not allowed to access data from non main branches"). `sonar.yml` was
restricted to `main` and pull requests accordingly.

Taken together, the two decisions mean a milestone's code is not analysed until the
milestone is finished. Every issue the gate would raise, across all of a milestone's
tickets, arrives at once, at review time, when fixing it is most expensive. M0 already
spans six tickets, and later milestones are larger.

How can every push to a milestone branch be analysed, within the current plan?

## Decision Drivers

- The quality gate should judge each push, not only the finished milestone.
- No paid plan.
- Keep what ADR-0014 achieved: one pull request per milestone, reviewed once, merged with
  a merge commit, so `Closes #N` works.
- Integration stays a human decision. An automated assistant opens a pull request only
  when the maintainer asks, and never merges one.

## Considered Options

1. Keep ADR-0014 as is: the pull request, and so the first analysis, comes at the end.
2. Open the milestone's pull request as a **draft** when its branch is first pushed, and
   mark it ready for review when the milestone is complete.
3. Move to a SonarQube Cloud plan that analyses any branch.

## Decision Outcome

Chosen option: **2, a draft pull request from the start.** SonarCloud analyses pull
requests, drafts included, so every push to the branch is analysed. The gate judges the
milestone's whole diff against `main`, which is the change that will eventually be merged.

- When a milestone branch is cut and first pushed, a **draft** pull request into `main` is
  opened for it, on the milestone's GitHub milestone. The maintainer opens it, or an
  assistant does when the maintainer asks.
- Work continues on the branch as before. Each push updates the pull request, and its
  checks run.
- When the milestone is complete, the maintainer marks the pull request **ready for
  review**, reviews it, and merges it with a merge commit, as in ADR-0014.
- `ci.yml` keeps running on every push to every branch. Its `pull_request` trigger now
  runs only for pull requests from forks, which `push` does not cover. A same-repository
  pull request would otherwise run the same jobs twice for each commit.

M0's pull request, #138, was the first opened this way.

### Consequences

- Good, because every push to a milestone branch gets the quality gate, and issues are
  fixed in the ticket that introduced them.
- Good, because the pull request shows the milestone's progress: its commits, checks and
  the issues it will close, while the work is in progress.
- Good, because nothing else in ADR-0014 changes. Review still happens once per milestone.
- Bad, because a draft pull request stays open for the whole milestone, so it shows up in
  the pull request list and in notifications for weeks.
- Bad, because a draft can attract review comments on unfinished work. "Ready for review"
  is the signal that the milestone is complete and the review has started.
- Neutral, because `ci.yml` jobs still appear on a same-repository pull request, as
  skipped `pull_request` runs next to the `push` runs that did the work.

### Confirmation

- Every milestone branch on the remote has an open pull request into `main`, a draft
  until the milestone is complete.
- The `SonarQube` check appears on each push to a milestone branch.
- A push to a milestone branch runs each `ci.yml` job once.

## Pros and Cons of the Options

### 1. Keep ADR-0014 as is

- Good, because it needs no change.
- Bad, because the gate's findings arrive all at once, after the milestone is finished.

### 3. A plan that analyses any branch

- Good, because the workflow of ADR-0014 would stay exactly as written.
- Bad, because it costs money, for what a draft pull request gives for free.

## More Information

- ADR-0014 covers the branching model, and ADR-0004 the quality gate and the plan's limit.
- [`docs/contributing.md`](../contributing.md) describes the day-to-day workflow.
