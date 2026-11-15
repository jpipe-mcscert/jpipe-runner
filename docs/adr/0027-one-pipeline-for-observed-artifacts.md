---
status: accepted
date: 2026-11-15
decision-makers: Sébastien Mosser
---

# ADR-0027: One definition of what a glob designates, a report that keeps what each file was declared as, and observation in three steps

## Context and Problem Statement

An evidence declares the files it observes (ADR-0018); a run reaches, records and injects
them (ADR-0019); the report lists them (ADR-0011), and `impact` and `status` read it
(ADR-0025). Built over four milestones, the mechanism works, with three seams:

- **A glob is matched in three ways.** A run lists files with `Path.glob`. `impact` asks
  whether a glob matches a path with a function of its own. The dataflow diagram finds
  the unreachable files of a glob with `fnmatch`, whose `*` crosses `/`: `build/*.xml`
  takes `build/old/a.xml` for its own. And `Path.glob` itself differs between versions of
  Python: a trailing `**` is directories only before 3.13, so `src/**` observes nothing
  on 3.11, while `impact` says a change under `src/` affects the evidence.
- **The report forgets what each file was declared as.** An element's `artifacts` is a
  flat list of files. Which path or glob of `observes` designates each one is known when
  it is recorded, then dropped; the diagram and `status` find it again by matching, and
  `status` guesses that an unreachable artifact whose name holds a wildcard is a glob
  that matched nothing.
- **`observe` does three things at once**: it finds the files, hashes them and builds the
  step's arguments, and none can be had without the others. `impact` keeps a copy of the
  check that a file can be read.

## Decision Drivers

- **A glob means one thing**, in a run, in `impact`, in `status` and in a diagram.
- **The report is the contract** (ADR-0011): what a reader needs is in it, not derived
  again, and a report of 4.0.0 archived with a release stays readable.
- **No behaviour without a user**: the parts are separated; nothing new runs.

## Considered Options

For the glob:

1. One module defines both operations, listing and matching, and a test holds them equal.
2. One operation only: list by walking the tree under the root and matching each file.

For the report:

3. Add `declared` to each artifact, in schema 1.1.
4. Nest the files under what declares them (`observes` as objects), in schema 2.0.

## Decision Outcome

Chosen options: **1** and **3**, and `observe` as the composition of three functions.

- **`artifacts` defines what a glob designates.** `files(pattern, root)` lists the regular
  files it matches, sorted; `matches(path, pattern)` says whether it would match a path,
  without the file system, since a changed file may be gone. Nothing else matches a glob:
  `impact` and `status` call them, and the diagram matches nothing. A property test checks
  that `matches` accepts exactly what `files` lists.
- **A trailing `**` designates the files below it**, on every version of Python: `files`
  lists `src/**` as `src/**/*`. This closes the difference ADR-0025 kept on purpose.
- **Each artifact of the report says what it was `declared` as**: the path or glob of its
  element's `observes`. For a path, and for a glob that matched nothing, it is the
  artifact's `path`. A file that two declarations designate is listed under each: a
  record is a declaration and a file. The schema becomes **1.1**, and `declared` is
  optional in it, as its versioning rule requires.
- **A reader of 1.1 reads 1.0.** `status` reads a report of any minor version of its
  major: the fields of a later one are ignored, and `declared` is not required of an
  earlier one, for which `status` falls back on the name of the file.
- **Observation is three functions.** `locate(artifact, root)` finds the files, reading
  none, and the artifact so `Located` gives the step's argument. `record(located, root)`
  hashes each file into an `Observation`, which holds the `Obstacle` when the file could
  not be reached. `unreachable(observations, element)` turns the obstacles into `JP019`.
  `observe` composes them, and the engine calls it as before. `readable(file)` is the
  check without the hash, which `status` uses.
- **Not decided here**: a dry run still reaches no file (ADR-0024). The parts make it
  possible; whether a dry run should fail on a file a build has yet to write is a
  decision of its own.

### Consequences

- Good, because a run, `impact`, `status` and the diagrams agree on every glob, on every
  supported Python.
- Good, because a reader of the report, such as the GitHub Action, groups files by what
  declared them without matching anything.
- Good, because reachability, recording and arguments are tested, and usable, one by one.
- Bad, because `src/**` now observes files on Python 3.11 and 3.12, where it failed with
  `JP019`: an evidence that relied on that failure passes or fails on its step instead.
- Bad, because there are still two operations on a glob, kept equal by a test, not by
  construction.
- Neutral, because a consumer that validates reports against a copy of schema 1.0 must
  take 1.1: the schema is strict.

### Confirmation

- `tests/unit/test_artifacts.py` checks `files` and `matches`, one against the other on
  generated trees, and `locate`, `record`, `unreachable` and `readable` on their own.
- `tests/unit/test_impact.py` checks that a 1.0 report is read, and what `status` finds
  with and without `declared`.
- `tests/unit/test_json_report.py` and the golden reports check `declared`.

## Pros and Cons of the Options

### 1. Two operations in one module

- Good, because listing stays `Path.glob`, which does not walk what a glob cannot match.
- Bad, because their agreement is tested, not structural.

### 2. List by walking and matching

- Good, because there is one matcher.
- Bad, because every glob walks the whole tree under the root, `.git` and virtual
  environments included.

### 3. `declared` on each artifact

- Good, because it is an added, optional field: a minor version.
- Neutral, because a file under two declarations is listed twice.

### 4. Files nested under their declaration

- Good, because the structure says it, and no file is listed twice without reason.
- Bad, because it changes `observes` and `artifacts`: a major version of the contract,
  for every consumer, in a minor release of the runner.

## More Information

- [ADR-0018](0018-evidence-declares-observed-artifacts.md) and
  [ADR-0019](0019-evidence-observes-files.md), the mechanism;
  [ADR-0011](0011-json-report-is-the-machine-readable-contract.md), the report;
  [ADR-0025](0025-impact-and-staleness.md), whose matching this moves and whose trailing
  `**` difference it closes.
