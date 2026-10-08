---
status: accepted
date: 2026-10-09
decision-makers: Sébastien Mosser
---

# ADR-0019: Evidence observes files, recorded just before its step runs

## Context and Problem Statement

ADR-0018 has an evidence declare the artifacts it observes, as a file, a directory
(`"src/"`) or a glob, and has the runner fail an evidence whose artifact cannot be reached.
It left the run-time half to M4 (#144): what "cannot be reached" means, what the runner
records of a reachable artifact, and when.

A file has an obvious record: its path, its SHA-256 and its size. A directory has none.
It could be recorded as a path only (which says nothing about what the step saw), as one
entry per file under it (thousands of lines for `src/` or `docs/`), or as one digest of
its tree (a format of our own, which every consumer would have to learn). Every evidence
written so far, in the scenarios, the examples and the step libraries in use, observes
files: the directory form has no user yet.

## Decision Drivers

- **What is recorded is what the step saw**, so that a reader can trust the verdict and
  staleness (#146) can compare runs.
- **The report stays readable**, and its format (#122, #145) simple to consume.
- **No feature without a user.** A form nobody uses still has to be specified, tested and
  documented, and kept compatible once released.

## Considered Options

1. Keep directories, recorded by their path only.
2. Keep directories, recorded as one entry per file under them.
3. Keep directories, recorded as one digest of their tree.
4. Drop directories for now: an evidence observes files, one by name or several by glob.

## Decision Outcome

Chosen option: **4, evidence observes files**, because files are all that evidence
observes today, and each of the other options either records nothing of a directory's
content or adds a record format without a user. A glob such as `"src/**/*"` observes the
files a directory holds, and records each one. Directories can come back, with their own
ADR, when an evidence needs one.

This amends ADR-0018, which allowed directories:

- **A path that ends with `/` is refused when the library is imported**, with a
  `TypeError` that suggests the glob of its files. A glob ending with `/` was already
  refused.
- **An artifact is observed just before its step is called**, and only if it is called:
  an evidence blocked by a supporter that did not pass (a cross-check, ADR-0013) observes
  nothing.
- **Reachable** means a file that exists and can be read, or a glob that matches at least
  one file, each of which can be read. A glob matches as pathlib does: `**` matches any
  depth, and directories it matches are ignored. Symbolic links are followed.
- **Unreachable** is a missing file, a broken link, a file that cannot be read, a path
  that names a directory, or a glob that matches no file. Each is reported with
  `JP019` `UnreachableArtifact`, an error: the step is not called and the evidence fails.
  Every unreachable artifact of the evidence is reported, not only the first.
- **Recorded**: for each file, its path relative to the run's root, its SHA-256 and its
  size, from a single read. An unreachable artifact is recorded too, without a digest, so
  that the report can list it next to its diagnostic (#145).
- **Injected**: the step receives a `Path` for a file, and the sorted `list[Path]` of the
  files a glob matches.

### Consequences

- Good, because every record is a file with a digest that standard tools reproduce
  (`sha256sum`).
- Good, because one format covers both forms, and the report (#145) needs no other.
- Bad, because an evidence that wants "the directory" writes a glob, and its step
  receives the files rather than the directory.
- Bad, because a glob over a large tree reads every file it matches, on every run.

### Confirmation

- `tests/unit/test_steps.py` checks that a directory is refused at import.
- `tests/unit/test_artifacts.py` checks reachability, the records and the arguments.
- From #120, the engine tests check that an unreachable artifact fails the evidence
  without calling it.

## Pros and Cons of the Options

### 1. Directories, by path only

- Good, because it is cheap.
- Bad, because the record says nothing of the content the step saw: a verdict could not
  be told stale.

### 2. Directories, one entry per file

- Good, because the record is complete, in the format of files.
- Bad, because the report of an evidence over `src/` lists every file under it.
- Neutral, because a glob gives the same record, when it is wanted.

### 3. Directories, one tree digest

- Good, because the record is one line, and changes with any file under the directory.
- Bad, because the digest is a format of our own, to specify and keep stable.
- Bad, because nothing uses it yet.

### 4. Files only

- Good, because there is one record format, and one less form to document and test.
- Bad, because it takes back part of ADR-0018 before any release used it.

## More Information

- [ADR-0018](0018-evidence-declares-observed-artifacts.md), which this amends;
  [ADR-0013](0013-kind-divergence-under-composition.md), cross-checks.
- #144 (this decision), #145 (artifacts in the report), #146 (staleness).
