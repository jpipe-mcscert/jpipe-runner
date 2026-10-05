# Architecture Decision Records

Decisions about jpipe-runner's design and the way it is built, in
[MADR](https://adr.github.io/madr/) format. Records are numbered and immutable once
accepted. Reversing a decision means writing a new ADR that supersedes the old one.

The v4 issues reserved ADR-0001 to ADR-0013 in advance. Each one is written when its
issue lands. A new decision takes the next number after the highest one in this table,
reserved or not.

To write one, copy [`template.md`](template.md) to `NNNN-short-title.md`, fill it in,
and add a row to this table.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-consume-compiler-json.md) | Consume compiler-produced JSON rather than parse `.jd` | accepted |
| [0002](0002-rewrite-from-scratch.md) | Rewrite from scratch on a branch rather than port v3 | accepted |
| [0003](0003-drop-sphinx-markdown-docs.md) | Drop Sphinx; docs are task-oriented Markdown | accepted |
| [0004](0004-sonarcloud-quality-gate.md) | SonarCloud as the quality gate | accepted |
| 0005 | Outcomes as return values instead of a `produce` callable | reserved ([#113](https://github.com/jpipe-mcscert/jpipe-runner/issues/113)) |
| 0006 | One decorator per kind | reserved ([#114](https://github.com/jpipe-mcscert/jpipe-runner/issues/114)) |
| 0007 | Binding resolution, and why elements carry several ids | reserved ([#115](https://github.com/jpipe-mcscert/jpipe-runner/issues/115)) |
| 0008 | Drop external variable injection | reserved ([#114](https://github.com/jpipe-mcscert/jpipe-runner/issues/114)) |
| 0009 | Separate the declaration registry from the per-run value store | reserved ([#117](https://github.com/jpipe-mcscert/jpipe-runner/issues/117)) |
| 0010 | Diagnostics as data, rules as objects, real severity levels | reserved ([#118](https://github.com/jpipe-mcscert/jpipe-runner/issues/118)) |
| 0011 | The JSON report is the machine-readable contract | reserved ([#122](https://github.com/jpipe-mcscert/jpipe-runner/issues/122)) |
| 0012 | Extract the GitHub Action to its own repository | reserved ([#130](https://github.com/jpipe-mcscert/jpipe-runner/issues/130)) |
| 0013 | Kind divergence under composition is a warning, not an error | reserved ([#119](https://github.com/jpipe-mcscert/jpipe-runner/issues/119)) |
| [0014](0014-trunk-with-milestone-branches.md) | A single `main` trunk, one pull request per milestone | accepted, amended by [0015](0015-draft-pull-request-per-milestone.md) |
| [0015](0015-draft-pull-request-per-milestone.md) | Open each milestone's pull request as a draft when the milestone starts | accepted |
