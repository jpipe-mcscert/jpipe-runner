---
status: accepted
date: 2026-11-15
decision-makers: Sébastien Mosser
---

# ADR-0028: An evidence observes observables, and a path is relative to the file that declares its step

## Context and Problem Statement

An evidence declares the artifacts it observes, each a path relative to the directory the
runner runs in (ADR-0018), and an artifact is a file (ADR-0019). 4.0.0 shipped that, and
two problems with it:

- **The same library observes different files depending on where the command is typed.**
  `jpipe-runner --library justifications/steps.py` run from the repository and from
  `justifications/` look for `CHANGELOG.md` in two places. The troubleshooting page had a
  section for it: every evidence fails, `cd` somewhere else. A library does not say where
  it must be run from, so nothing in it tells its reader what its paths mean.
- **Evidence observes more than files.** A release is ready when the version in
  `package.json` is the one announced, when the pipeline runs on the release branch. The
  version is a value in a file; the branch is an environment variable. Today a step reads
  them itself, undeclared: the report does not say they were relied on, and an evidence
  that reads nothing but the environment is `JP018`.

What are an evidence's paths relative to, and how does it declare what is not a file?

## Decision Drivers

- **A library means one thing**, wherever the runner is started.
- **What is relied on is declared** (ADR-0018), whatever it is: recorded in the report,
  and never optional.
- **An extension point, not a list**: a step library observes what the runner has no
  class for.
- **The report stays a 1.x contract** (ADR-0011): its paths, and what `impact` and
  `status` do with them, do not change.
- **A step stays a plain function**: it receives values, and a test passes its own.

## Considered Options

For the paths:

1. Relative to the working directory, as in 4.0.0.
2. Relative to the file that declares the step.
3. Relative to a project root, given with an option or found by a marker (`.git`,
   `pyproject.toml`).
4. Relative to the justification's JSON file.

For what is observed:

5. More keywords on the decorator: `observes_env=`, `observes_json=`.
6. An abstract class, `Observable`, with the built-in kinds as its subclasses.

## Decision Outcome

Chosen options: **2** and **6**.

```python
@evidence(
    "release:e4",
    observes={
        "changelog": "../CHANGELOG.md",
        "version": JsonValue("../package.json", "/version"),
        "branch": Env("GITHUB_REF_NAME", display=True),
    },
    produces=["releasable"],
)
def the_release_is_configured(changelog: Path, version: str, branch: str) -> Outcome: ...
```

- **A path is relative to the directory of the file that declares the step**, as a link in
  a page is relative to the page. The decorator reads it from the function's code (through
  `functools.wraps`, from the function a wrapper wraps), and keeps it on the `Step`. A
  function with no file, typed at a prompt, is in the working directory.
- **This corrects 4.0.0, in a minor release.** A library beside the files it observes,
  run from its directory, as every example and scenario is, observes what it did. One in
  a subdirectory run from the repository's root now looks from its own directory: its
  evidence fails with `JP019`, which names where it looked and says what a path is
  relative to. Keeping both meanings, one for a string and one for a `File`, would keep
  the confusion.
- **The report does not change its paths.** `observes`, `artifacts[].path` and the
  messages show a file relative to the directory the runner runs in, the name a changed
  file has in `git diff`. `Context.shown` turns a declared path into that one, following
  links to find the two directories and never in the path itself. `impact` and `status`
  work as before, and `status` still runs where the run ran.
- **What an evidence observes is an `Observable`**, an abstract class with three methods:
  `describe(context)`, how the report names it; `observe(context)`, what it is now;
  `depends_on(context)`, the files a change to which reaches it, none by default. A
  string in `observes` stands for `File`. It is hashable, as a `Step` is.
- **`observe` returns a `Sighting`**: the value the step receives, and an `Observation` of
  each thing seen, with its SHA-256, or the `Obstacle` that kept it from being seen. An
  obstacle is `JP019`, and the step is not called: nothing observed is optional
  (ADR-0018). An observable that raises is an obstacle, not a crash.
- **Three are built in.** `File(path)`: a file, or a glob of files, as before.
  `JsonValue(path, pointer)`: the value a JSON Pointer (RFC 6901) designates in a file;
  the step receives the value; the file is recorded as a file, with the value, and a
  change to it reaches the evidence. `Env(name, display=False)`: an environment variable;
  the step receives its value.
- **Everything observed is recorded, and the abstraction enforces it.** A `Sighting`
  holds at least one observation, and a reachable `Observation` holds the SHA-256 of what
  was seen or says that it is `hidden`: constructing one with neither, or with both, is
  an error. An observable of a step library therefore cannot observe off the record.
- **A variable is hidden unless its step says so.** By default the report records that
  it was observed, and neither its value nor its SHA-256, which would let a short secret
  be guessed. `display=True` records both.
- **The report grows, in schema 1.1** (ADR-0027, not released). An element gains
  `sources`, everything its step declares, as each describes itself, and `observations`,
  what it observed that is not a file, each with its `variable`, if it is one, and
  whether it is `hidden`. `observes` keeps its meaning for a reader of 1.0,
  paths and globs: it is now the files the sources depend on. An artifact may carry the
  `value` observed in it.
- **`status` answers for everything a run observed, or does not answer.** It reads a
  report and imports no library (ADR-0025). A file is compared by its SHA-256, a
  `JsonValue` through its file, and an environment variable by the SHA-256 of its value:
  an observation names its `variable`, so the report is enough to read it again. What the
  report hides cannot be compared: `status` then says that information was hidden and
  that a new run is needed, exits 1, and never says that the report holds. Hiding a value
  is choosing to run again. What is neither a file nor a variable, reached by an
  observable of a step library, gets the same answer: only that library can observe it
  again.
- **`observe` is no longer three functions.** ADR-0027 took it apart into `locate`,
  `record` and `unreachable`; each observable now does the first two for what it
  observes, and `artifacts.observe` only collects. What a glob designates moves to
  `observables`, with the classes that use it.

### Consequences

- Good, because a library can be read, and run, without knowing where the command is
  typed.
- Good, because an evidence that rests on a variable or on one value of a file declares
  it, and its report says so.
- Good, because a step library adds a kind of evidence without a change to the runner.
- Bad, because a 4.0.0 library in a subdirectory, run from elsewhere, must have its paths
  rewritten from its own directory.
- Bad, because a library in a subdirectory reaches the files of its repository through
  `..`.
- Bad, because a library installed as a package cannot observe the files of the project
  it is run on: its paths start in `site-packages`. An explicit anchor on `File` can
  come with the first such library.
- Bad, because a report that hides a value, or holds what only a library can observe, is
  never confirmed by `status`: it takes a run.
- Bad, because `impact` follows files only: a change to a variable reaches no evidence.
- Neutral, because the compiler's exporter writes `observes={}`, which means what it did.

### Confirmation

- `tests/unit/test_observables.py` checks `Context.shown`, that a library observes the
  same file from two working directories, and `File`, `JsonValue` and `Env`.
- `tests/unit/test_artifacts.py` checks that a run collects them, and what an observable
  that raises becomes.
- `tests/unit/test_steps.py` checks that a step keeps the directory of its file.
- The `simple_import` scenario has its library in a subdirectory, and observes files
  beside it and above it; `observables` is a scenario with a `JsonValue` and an `Env`.
- `tests/unit/test_observables_doc.py` runs `docs/observables.md` on that scenario: its
  observables, its console sessions and the report it quotes.

## Pros and Cons of the Options

### 1. The working directory

- Good, because a path is the one `git diff` prints.
- Bad, because a library's meaning depends on where its command is typed.

### 2. The declaring file

- Good, because it is what a reader of the file expects, with nothing to configure.
- Bad, because of `..`, and of libraries installed as packages.

### 3. A project root

- Good, because paths read as paths of the repository.
- Bad, because the question moves to which directory is the root, and a marker that is
  found differs between a checkout, an archive and a container.

### 4. The justification file

- Bad, because it is the compiler's output, often in a build directory.

### 5. More keywords

- Good, because nothing is imported.
- Bad, because each kind is a change to every decorator signature, to the compiler's
  exporter, and to the runner: a step library cannot add one.

### 6. An abstract class

- Good, because one mapping declares everything a step receives, and a library derives
  its own.
- Neutral, because an observable of a library is code the runner calls before the step.

## More Information

- [ADR-0018](0018-evidence-declares-observed-artifacts.md) and
  [ADR-0019](0019-evidence-observes-files.md), which this amends: a path's anchor, and
  what an artifact is; [ADR-0027](0027-one-pipeline-for-observed-artifacts.md), whose
  third decision it replaces; [ADR-0025](0025-impact-and-staleness.md), impact and
  staleness; [ADR-0011](0011-json-report-is-the-machine-readable-contract.md), the report.
