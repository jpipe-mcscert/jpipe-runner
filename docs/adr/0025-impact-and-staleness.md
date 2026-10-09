---
status: accepted
date: 2026-10-09
decision-makers: Sébastien Mosser
---

# ADR-0025: Impact and staleness are read from the declarations and the report

## Context and Problem Statement

Evidence declares the files it observes (ADR-0018, ADR-0019), and the JSON report records
what each run observed, with each file's SHA-256, beside what each element supports
(ADR-0011). Two questions developers ask can be answered from that alone, without running
a step (#146):

- **Impact:** which claims does this change put in question? A pull request that edits
  `build/tests.log` reaches the evidence that observes it, and everything above it. The
  GitHub Action (MB1) can say so in a comment on every pull request, if it is cheap.
- **Staleness:** does an earlier verdict still hold? A report archived with a release says
  what the run read; if one of those files has changed since, the elements above it are
  no longer established by that run.

#146 also asked for a run of only the affected evidence and what it supports. Such a run
judges part of an argument: what its verdict is, and what the report says of the elements
it did not run, is a decision of its own.

## Decision Drivers

- **No step runs**: both must be cheap enough for every pull request, and safe to run on
  a branch nobody has reviewed.
- **One source of truth**: what the runner declared and observed is the report, the
  contract other tools read (ADR-0011).
- **A file matches as the runner observes it**: a glob must mean in `impact` what it means
  when an evidence observes it.
- **Honest limits**: what is not declared cannot be seen.

## Considered Options

1. Read the report: the report of a dry run for impact (ADR-0024), the report of a run for
   staleness.
2. Read the model and the step registry directly, through their Python objects.
3. Keep a separate index of files to evidence, written by each run.

## Decision Outcome

Chosen option: **1, read the report**, because it is the contract the Action will read
too, and it already carries everything both questions need: `supports`, `observes` and
`artifacts`.

- **`impact`** runs a dry run, which imports the step libraries and binds them but calls
  no step, and works on its JSON document. A changed file reaches each evidence one of
  whose declared paths matches it, and each element above that evidence, following
  `supports`. Changed files no evidence observes are listed as such: the argument does
  not cover them. The changes are given with `--changed PATH`, repeated, or with
  `--since REF`: what `git diff --name-only --relative REF` lists, and the untracked files
  git does not ignore. Git is asked before the libraries are imported, since an import
  writes files of its own. A revision that starts with `-` is refused, so that it cannot
  be read as an option of git. The exit code is 0 whatever the change reaches: the
  command informs, it does not judge.
- **A path matches as `Path.glob` matches it**: each segment as `fnmatch` does, case
  sensitive, and `**` for any number of segments, none included; no regular expression is
  built. A property test checks `matches` against `Path.glob` on generated trees. One
  difference is kept on purpose: a trailing `**` matches the files below it, which
  `Path.glob` does only from Python 3.13; it can only make `impact` report more.
- **`status REPORT`** reads a report, refuses one whose schema's major version it does not
  know, or that does not match the schema, and compares each file the run observed with
  the file now, under the working directory: `changed` (another SHA-256), `vanished` (read
  then, gone or unreadable now), `appeared` (unreadable then, there now), and `added` (a
  file a declared glob matches now that the run did not see). It lists them, then the
  elements above the evidence that observed them, and exits 1 if there is any, 0
  otherwise. A report of a run in which no step ran (`invalid`, `valid`) observed nothing,
  and is refused (3). The report does not record the directory it was run in, so `status`
  runs from there; when every file it recorded is missing, it warns that it is probably
  run from elsewhere.
- **Both print text, for people.** The Action can quote it in a comment. A JSON form would
  be a second contract to version; it can come when a program needs it.
- **Running only what a change affects is split out** of #146, into #153: a partial run
  needs a decision on its verdict and on what its report says of the elements it did not
  run. So is reusing the outcome of unchanged evidence (`--incremental`).

### Consequences

- Good, because neither question runs a step, so both are cheap and safe on any branch.
- Good, because `impact` and `status` read the same contract as the Action, so the report
  is exercised by the runner itself.
- Good, because a change the argument does not cover is visible.
- Bad, because both are only as good as the declarations: a file a step reads without
  declaring it is invisible. `JP018` catches only the extreme case, an evidence that
  observes nothing.
- Bad, because `status` must run in the directory the run ran in.
- Neutral, because the text output is not a contract.

### Confirmation

- `tests/unit/test_impact.py` checks matching, against `Path.glob` too, the elements
  reached, each kind of change, reading a report, and git.
- `tests/unit/test_cli.py` checks both subcommands and their exit codes; `tests/e2e/test_cli.py`
  runs `impact --since` in a git repository.
- `tests/unit/test_cli_doc.py` replays the examples of `docs/cli.md`.

## Pros and Cons of the Options

### Read the report

- Good, because the report is already the contract, and carries `supports`, `observes`
  and `artifacts`.
- Bad, because impact needs a dry run, which imports the libraries.

### Read the model and the registry

- Good, because nothing is serialized.
- Bad, because `status` would need the libraries and the model of the past run, which the
  report already summarizes.

### A separate index

- Good, because it could be read without importing anything.
- Bad, because it is a second record of what the report records, to keep in step.

## More Information

- #146 (this decision), #153 (partial runs), #132 (the Action), #143, #144, #145 (observed
  artifacts).
- [ADR-0011](0011-json-report-is-the-machine-readable-contract.md), the report;
  [ADR-0019](0019-evidence-observes-files.md), observed files;
  [ADR-0023](0023-the-command-line.md), the command line;
  [ADR-0024](0024-dry-run-verdict-and-both-diagrams.md), the dry run.
