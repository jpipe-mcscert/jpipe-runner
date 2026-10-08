---
status: accepted
date: 2026-10-08
decision-makers: Sébastien Mosser
---

# ADR-0017: Document a feature in the milestone that builds it; M7 reviews the whole

## Context and Problem Statement

The v4 plan put all user documentation in the last milestone, M7 Docs: the tutorial
(#125), the authoring guide (#126), the CLI reference (#127), the rules reference (#128),
and the README and migration guide (#129). Each of M0 to M6 was to build features, and M7
to describe them.

M2 showed the cost of that split. Its pull request (#141) changed the authoring API in
ways #126 had been written against: binding became one to one, while #126's acceptance
list still asks to document "one function → many elements" as a capability. The decisions
were fresh in M2, recorded in its ADRs, and would have had to be reconstructed five
milestones later from those ADRs and the code. Meanwhile, the only description of the
authoring API a reader could find was scattered across ADRs and the
[progress page](../v4-progress.md).

When should user documentation be written (#141 review)?

## Decision Drivers

- **Documentation written with the code is accurate.** The person who just made the
  decisions knows them, and a reviewer of the milestone can check the docs against the
  code in one pull request.
- **Every merged milestone is usable from its docs.** A reader of `main` finds a
  description of each feature that exists, not a promise of one.
- **The documentation set is still read as a whole.** Pages written over several
  milestones drift in terms, depth and structure, and need one pass to make them
  consistent.

## Considered Options

1. Keep the plan: all user documentation in M7.
2. Document each feature in the milestone that builds it; M7 reviews the whole for
   consistency and completes the public API documentation.

## Decision Outcome

Chosen option: **2, document in the milestone that builds it**, because it is the only
option where the documentation is written when the decisions are known, and checked in the
same review as the code.

- **A milestone that adds or changes something a user sees documents it under `docs/`**,
  in its own pull request, like the CHANGELOG and [`v4-progress.md`](../v4-progress.md).
  Examples in those pages are executed by the test suite where they are code.
- **The documentation issues move to the milestone that builds what they describe:**

  | Issue | Page | Milestone |
  |---|---|---|
  | #126 | `docs/authoring.md`, the authoring guide | M2 Authoring API |
  | #128 | `docs/rules.md`, generated from the rules | M3 Validation |
  | #127 | `docs/cli.md` and `docs/report-schema.md` | M6 CLI (the report schema with M5) |
  | #125 | `docs/tutorial.md`, from `.jd` to a green run | M6 CLI, the first milestone that can run one |

- **M7 becomes a review:** it reads the documentation as a whole for consistency of terms
  and structure, checks that the public API is completely described, and writes what
  belongs to no single milestone: the README, troubleshooting, the migration guide and
  `CLAUDE.md` (#129).

### Consequences

- Good, because each page is written while its decisions are fresh, and reviewed with the
  code that it describes.
- Good, because `main` documents every feature it has after each merge.
- Bad, because each milestone carries more work, and its pull request is longer.
- Bad, because pages written separately may disagree until M7 reconciles them. The review
  is planned for that reason, rather than assumed unnecessary.

### Confirmation

- Each milestone's pull request contains the pages for what it adds; its review checks
  them.
- `CLAUDE.md` (Branching) and `docs/contributing.md` (Working on a milestone) state the
  rule.
- The documentation issues are on the milestones in the table above.

## Pros and Cons of the Options

### 1. All documentation in M7

- Good, because milestones before M7 stay focused on code.
- Bad, because decisions are documented long after they are made, from memory and ADRs.
- Bad, because the plan's documentation issues go stale as the code departs from them, as
  #126 did in M2.

### 2. Document in the milestone, review in M7

- Good, because the documentation tracks the code from the start.
- Bad, because the work is spread over every milestone instead of one.

## More Information

- #141, the M2 pull request, whose review raised this.
- [ADR-0003](0003-drop-sphinx-markdown-docs.md): v4 documentation is task-oriented
  Markdown under `docs/`.
