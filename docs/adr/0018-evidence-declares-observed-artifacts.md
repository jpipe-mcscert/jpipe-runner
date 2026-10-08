---
status: accepted
date: 2026-10-08
decision-makers: Sébastien Mosser
---

# ADR-0018: Evidence declares the artifacts it observes

## Context and Problem Statement

Evidence is where a justification touches the world. "The test suite passes" is true of a
test report; "the changelog is up to date" is true of a file. Up to M2, which artifacts an
evidence read was a convention: a step opened whatever paths it liked, and nothing
recorded which. The runner could not:

- tell that an evidence checks nothing at all, such as a placeholder that returns `Pass()`
  or a skeleton the compiler generated and nobody filled in;
- check, before trusting a verdict, that the artifacts behind it exist;
- show a reader of the verdict which artifacts it rests on, or hand them to CI to archive
  (the GitHub Action keeps a run's artifacts with its report);
- say which justifications a change to a file affects, or which verdicts are stale (#146).

How should an evidence's artifacts become known to the runner (#143)?

## Decision Drivers

- **Fake evidence is worse than missing evidence.** In an assurance case, a check that
  looks real and touches nothing misleads its readers.
- **What is recorded is what was relied on**, not every file the process happened to open.
- **Known before running.** Impact analysis and staleness (#146) need the artifacts of an
  evidence without running it.
- **A step stays a plain function**, testable without the runner (ADR-0005, ADR-0006).
- **A library works on every machine**, in CI as on a laptop.

## Considered Options

1. Keep the convention: steps open what they like, and nothing is recorded.
2. Trace file access at run time, with audit hooks (`sys.addaudithook`).
3. Declare the artifacts as data the step opens itself: `observes=["CHANGELOG.md"]`.
4. Declare the artifacts and inject them: `observes={"changelog": "CHANGELOG.md"}`, passed
   to the parameter `changelog`.

## Decision Outcome

Chosen option: **4, declared and injected artifacts**, because it is the only one that
records what an evidence relies on before it runs, and keeps the step's code and its
declaration from drifting apart: the step can only read what it was given.

```python
@evidence("release:e2", observes={"changelog": "mock/CHANGELOG.md"}, produces=["changelog_ok"])
def the_changelog_is_up_to_date(changelog: Path) -> Outcome: ...
```

- **`observes` maps a parameter name to a path.** The runner passes each artifact to the
  function under that name (M4, #144), so a step never resolves a path itself, and a test
  passes its own: `the_changelog_is_up_to_date(changelog=tmp_path / "CHANGELOG.md")`.
- **Only `@evidence` takes `observes`.** This completes the symmetry of ADR-0006: evidence
  observes artifacts and produces values; strategies consume values and produce values. A
  strategy that needs a file has an evidence inside it.
- **A path names a file, a directory or a glob of files.** A directory is written with a
  trailing `/` (`"src/"`), so the declaration says which it is, and its parameter receives
  a `Path`. A glob (`"build/reports/*.xml"`) matches files, and its parameter receives
  their sorted `list[Path]`. A glob that ends with `/`, matching directories, is refused:
  observe the directory without wildcards, or its files.
- **Paths are relative to the run's working directory.** An absolute path is a `TypeError`
  when the library is imported: it would tie the library to one machine, and impact
  analysis compares paths within the repository.
- **An observed artifact is never optional.** An artifact that cannot be reached, a
  directory that does not exist or a glob that matches nothing, fails the evidence (M4).
  A check like "no crash dump exists" does not declare the file it hopes is absent.
- **Every observed artifact is declared.** There is no run-time way to record an
  undeclared one: evidence consumes nothing, so its paths can depend only on the
  environment, and a glob covers "whichever file is there". An artifact recorded only at
  run time would be invisible to impact analysis and staleness (#146).
- **Every evidence observes something.** An evidence step that declares no artifact is
  `JP018` `EvidenceObservesNothing`, an **error**: it checks nothing in the world, whatever
  it returns.
- **The report lists every observed artifact** (#145): for a directory, the directory; for
  a glob, each file it matched. A CI pipeline, such as the GitHub Action, archives them
  with the verdict.
- **Spelling: `artifact`**, the Canadian spelling, in identifiers, the report and the
  documentation. It is also SACM's ("Artifact") and the jPipe skills' spelling.

Import-time checks raise a `TypeError`, as for the rest of the declaration: `observes` is
a mapping, its keys are Python identifiers, and its values non-empty relative paths. The
function's parameters match the observed names as other steps' match their consumed
variables: every observed name is a parameter that can be passed by keyword (or
`**kwargs` takes it), and every parameter without a default is observed.

### Consequences

- Good, because placeholder evidence is caught by validation, before anything runs.
- Good, because the artifacts of every evidence are known statically, for the report,
  for archiving and for impact analysis.
- Good, because a step receives `Path`s and is tested with temporary files, without the
  runner and without changing the working directory.
- Bad, because a step that computes its paths (from an environment variable, say) must
  find a static path or glob that covers them.
- Bad, because every evidence of a v3 library, and every skeleton jPipe 2.5.0 generates,
  must be given its artifacts: until then each is `JP018`. The compiler's exporter cannot
  know them (#140).

### Confirmation

- `tests/unit/test_steps.py` checks the declaration and every import-time refusal.
- `tests/unit/validation/rules/test_evidence_observes_nothing.py` checks `JP018`.
- `tests/unit/test_scenario_corpus.py` checks that every artifact a scenario observes is
  in it.
- From M4, reachability; from M5, the report's artifacts (#144, #145).

## Pros and Cons of the Options

### 1. Convention only

- Good, because nothing changes.
- Bad, because none of the four needs in the context can be met.

### 2. Tracing with audit hooks

- Good, because a library needs no change.
- Bad, because it records too much (imports, libraries' own files, caches) and too
  little (subprocesses, the network), and records what was opened, not what was relied
  on.
- Bad, because nothing is known until the step has run.

### 3. Declared, opened by the step

- Good, because artifacts are known statically.
- Bad, because the declaration and the paths the code opens can drift apart, and a test
  must recreate the run's working directory.

### 4. Declared and injected

- Good, because the declaration is the only way the step gets its artifacts.
- Neutral, because a step gains one parameter per artifact.

## More Information

- #143 (this decision); #144 (reachability, recording and injection, M4), #145 (the report,
  M5), #146 (impact analysis, M6); #140 (the compiler's exporter).
- [ADR-0006](0006-one-decorator-per-kind.md), one decorator per kind;
  [ADR-0010](0010-diagnostics-as-data-rules-as-objects.md), the rules.
