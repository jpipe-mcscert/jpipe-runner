# Architecture Decision Records

Decisions about jpipe-runner's design and the way it is built, in
[MADR](https://adr.github.io/madr/) format. Records are numbered and immutable once
accepted. Reversing a decision means writing a new ADR that supersedes the old one. The
one exception is the retirement of the v3-to-v4 records below.

A new decision takes the next number after the highest one ever used, including the
retired numbers below.

Numbers 0002, 0014, 0015 and 0017 are retired. They recorded how v3 became v4 (the
rewrite, and the milestone branches it was built on), not decisions about the runner, and
were removed once v4 was released. They can still be read at the `v4.0.0` tag, for
instance `git show v4.0.0:docs/adr/0014-trunk-with-milestone-branches.md`.

To write one, copy [`template.md`](template.md) to `NNNN-short-title.md`, fill it in,
and add a row to this table.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-consume-compiler-json.md) | Consume compiler-produced JSON rather than parse `.jd` | accepted |
| [0003](0003-drop-sphinx-markdown-docs.md) | Drop Sphinx; docs are task-oriented Markdown | accepted |
| [0004](0004-sonarcloud-quality-gate.md) | SonarCloud as the quality gate | accepted |
| [0005](0005-outcomes-as-return-values.md) | Outcomes as return values instead of a `produce` callable | accepted |
| [0006](0006-one-decorator-per-kind.md) | One decorator per kind | accepted |
| [0007](0007-binding-resolution.md) | Binding resolution, and why elements carry several ids | accepted |
| [0008](0008-drop-external-variable-injection.md) | Drop external variable injection | accepted |
| [0009](0009-separate-registry-from-value-store.md) | Separate the declaration registry from the per-run value store | accepted, amended by [0031](0031-variables-resolve-among-supporters.md) |
| [0010](0010-diagnostics-as-data-rules-as-objects.md) | Diagnostics as data, rules as objects, real severity levels | accepted |
| [0011](0011-json-report-is-the-machine-readable-contract.md) | The JSON report is the machine-readable contract | accepted, amended by [0024](0024-dry-run-verdict-and-both-diagrams.md) and [0029](0029-the-runner-draws-the-dataflow.md) |
| [0012](0012-extract-the-github-action.md) | The GitHub Action leaves for jpipe-ci-actions, and runs v4 only | accepted |
| [0013](0013-kind-divergence-under-composition.md) | Kind divergence under composition is a warning, not an error | accepted |
| [0016](0016-hide-the-graph-inside-justification.md) | Hide the graph inside `Justification`; no NetworkX type in the public API | accepted, amended by [0010](0010-diagnostics-as-data-rules-as-objects.md) |
| [0018](0018-evidence-declares-observed-artifacts.md) | Evidence declares the artifacts it observes | accepted, amended by [0019](0019-evidence-observes-files.md) |
| [0019](0019-evidence-observes-files.md) | Evidence observes files, recorded just before its step runs | accepted |
| [0020](0020-importing-step-libraries.md) | Import step libraries as modules named after their files, for one run | accepted |
| [0021](0021-execution-semantics.md) | Failures and skips propagate as skips; a step's mistakes fail its element | accepted, amended by [0024](0024-dry-run-verdict-and-both-diagrams.md) |
| [0022](0022-diagrams-follow-the-compiler.md) | Diagrams follow the compiler's, with a status overlay and a dataflow view | superseded by [0029](0029-the-runner-draws-the-dataflow.md) |
| [0023](0023-the-command-line.md) | The command line: one command, its subcommands, its outputs and its exit codes | accepted, amended by [0029](0029-the-runner-draws-the-dataflow.md) and [0030](0030-a-run-streams-its-events.md) |
| [0024](0024-dry-run-verdict-and-both-diagrams.md) | A dry run validates and is `valid`; the report records both diagrams | accepted, amended by [0029](0029-the-runner-draws-the-dataflow.md) |
| [0025](0025-impact-and-staleness.md) | Impact and staleness are read from the declarations and the report | accepted |
| [0026](0026-dependency-ranges-and-freshness.md) | Runtime dependencies are tested ranges, and the lock file is kept fresh | accepted |
| [0027](0027-one-pipeline-for-observed-artifacts.md) | One definition of what a glob designates, a report that keeps what each file was declared as, and observation in three steps | accepted, amended by [0028](0028-observables-and-file-relative-paths.md) |
| [0028](0028-observables-and-file-relative-paths.md) | An evidence observes observables, and a path is relative to the file that declares its step | accepted |
| [0029](0029-the-runner-draws-the-dataflow.md) | The runner draws one diagram, the dataflow | accepted, amended by [0032](0032-a-run-previews-its-diagram.md) |
| [0030](0030-a-run-streams-its-events.md) | A run streams its events to a file, one JSON object per line | accepted, amended by [0032](0032-a-run-previews-its-diagram.md) |
| [0031](0031-variables-resolve-among-supporters.md) | A consumed variable resolves among its consumer's supporters | accepted |
| [0032](0032-a-run-previews-its-diagram.md) | A run draws its diagram before its first step, and a status never moves it | accepted |
| [0033](0033-a-value-is-recorded-as-it-was-seen.md) | A value is recorded as it was when the run saw it, even one that cannot be copied | accepted |
