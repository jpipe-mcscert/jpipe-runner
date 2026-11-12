# jpipe-runner — Project Guide for Claude

## Project Overview

`jpipe-runner` checks *jPipe justifications* by running them (v4, released as 4.0.0;
v3 frozen at 3.6.0). A justification, compiled by the jPipe compiler to JSON,
argues a claim from evidence and strategies; a **step library** binds a Python function to
each element (`@evidence`, `@strategy`, `@sub_conclusion`, `@conclusion`). The runner
validates the library against the model, runs the steps supporters first, and reports a
verdict as text, JSON and diagrams. It is a CLI (`jpipe-runner`, plus `impact` and
`status`) and an importable authoring API (`from jpipe_runner import …`). The GitHub Action
lives in the sibling repository `jpipe-mcscert/jpipe-ci-actions` (ADR-0012); it reads the
JSON report, so a change to its schema or to the exit codes reaches that repository.

- **Language**: Python ≥ 3.11
- **Build tool**: Poetry
- **Licence**: MIT
- **Distribution**: PyPI, Ubuntu PPA (Launchpad), Homebrew, GitHub Releases
- **Upstream**: `jpipe-mcscert/jpipe-runner`
- **Docs**: Markdown under `docs/`, indexed by [`docs/README.md`](docs/README.md); the
  words they use are defined in [`docs/concepts.md`](docs/concepts.md).

## Architecture

**[`docs/design.md`](docs/design.md) is the design**: a Mermaid module diagram and a
high-level class diagram (no members). Keep it in step with the code, in the same commit:
`tests/unit/test_design_doc.py` fails when a module is missing from the module diagram,
when its solid arrows are not exactly the imports between modules, or when a module's
public classes differ from its `namespace` in the class diagram. The page itself does not
mention tests or ADRs. Decisions are MADR records in [`docs/adr/`](docs/adr/README.md).

A run, as `cli.main` drives it:

```
cli.main                      argv → run | impact | status; exit codes 0–4 (ADR-0023)
  ├─ loader.load              compiler JSON → model.Justification; JP001–JP004 (ADR-0001)
  ├─ libraries.imported       step libraries imported as modules → steps.StepRegistry;
  │                           JP020, JP021 (ADR-0020)
  ├─ engine.run               (ADR-0021)
  │    ├─ validation + rules  binding.BindingTable, then every rule; JP005–JP016, JP018
  │    ├─ artifacts.observe   files an evidence observes, SHA-256; JP019
  │    ├─ the step, called    outcomes.as_outcome (JP017), JP022 if it raised
  │    └─ values.ValueStore   values produced in this run; JP023, JP024
  └─ report.RunReport         → text_report.render, json_report (report.schema.json),
                                diagram.write (DOT piped to Graphviz's dot, ADR-0022)
impact                        affected / stale / changed_since, from a JSON report (ADR-0025)
```

Key design choices:
- **Diagnostics are data, rules are objects** (ADR-0010): every problem is a `Diagnostic`
  with a stable `JPnnn` code; `docs/rules.md` is generated from `rules.py`. The next free
  code is the one after the highest in `rules.py`/`docs/rules.md`.
- **A step returns an outcome** (`Pass(values)`, `Fail(reason)`, `Skip(reason)`,
  ADR-0005); values live in a per-run `ValueStore`, not a global (ADR-0009).
- **Evidence declares the files it observes** (ADR-0018, ADR-0019); paths are relative to
  the working directory, the run's root.
- **The JSON report is the machine-readable contract** (ADR-0011), versioned and checked
  against `src/jpipe_runner/schema/report.schema.json`; the text report is for people.
- **The compiler co-owns the authoring API**: it generates step libraries
  (`PythonExporter.java` in `jpipe-compiler`), still for v3 as of jPipe 2.5.0 (#140).
  `jpipe_runner.framework` exists only to raise an `ImportError` that tells v3 users what
  replaced it.

## Critical Files

| File | Purpose |
|------|---------|
| `src/jpipe_runner/__init__.py` | The public API, loaded lazily: outcomes and the four decorators |
| `src/jpipe_runner/cli.py` | The command line: options, subcommands, outputs, exit codes |
| `src/jpipe_runner/steps.py` | The decorators, `Step`, `StepRegistry`, `observes` path checks |
| `src/jpipe_runner/engine.py` | `run()`: validation, then the steps supporters first; `RunResult`, `Verdict` |
| `src/jpipe_runner/rules.py` | Every validation rule; source of `docs/rules.md` |
| `src/jpipe_runner/binding.py` | Id resolution (exact, qualified, suffix) and the one-to-one `BindingTable` |
| `src/jpipe_runner/report.py` | `RunReport`, what every renderer reads |
| `src/jpipe_runner/schema/` | The JSON schemas of the compiler's justification and of the report |
| `pyproject.toml` | Dependencies, entry points, tool configuration |
| `.github/workflows/ci.yml` | CI — lint (ruff, mypy) and pytest on push to every branch, and on PRs to `main` |
| `.github/workflows/sonar.yml` | SonarCloud scan and quality gate (ADR-0004) |
| `.github/workflows/release.yml` | Multi-stage release pipeline (see Release section) |

## Testing

```bash
poetry install
poetry run pytest            # all tests, with coverage (writes coverage.xml)
poetry run pytest -m unit    # tests/unit/ only
poetry run pytest -m e2e     # tests/e2e/ only
poetry run ruff check . && poetry run ruff format --check .
poetry run mypy              # --strict, over src/
```

- All tool configuration (pytest, coverage, ruff, mypy) lives in `pyproject.toml`.
- The test architecture (rule tests, golden reports, property tests, the scenario format)
  is described in [`tests/README.md`](tests/README.md). `--update-goldens` regenerates the
  golden reports of the e2e scenarios and `docs/rules.md`, which is generated from the
  validation rules (`src/jpipe_runner/rules.py`) and checked by a test.
- **Every documentation page is tested** (`tests/unit/test_*_doc.py`, `test_readme.py`,
  `test_docs_links.py`): its code runs, its ```` ```console ```` sessions are replayed by
  `tests/console.py`, its quoted output is recomputed, and every link and anchor resolves
  (links to this repo's `main` branch are checked against the tree). Quote output the code
  printed, generated by running it, never typed by hand. `ruff format` also formats the
  ```` ```python ```` blocks of Markdown: wrap one that must stay verbatim in
  `<!-- fmt:off -->` / `<!-- fmt:on -->`.
- The `unit` / `e2e` markers are applied by `tests/conftest.py` from the test's directory.
  A test file outside `tests/unit/` or `tests/e2e/` is a collection error.
- `pre-commit install` runs ruff and mypy before each commit; CI's `lint` job runs the same.
- The quality gate is SonarCloud (`sonar-project.properties`, `.github/workflows/sonar.yml`,
  [ADR-0004](docs/adr/0004-sonarcloud-quality-gate.md)); it reads the `coverage.xml` pytest writes.

## Spelling

**Canadian spelling, project-wide**: prose, docs, ADRs, CHANGELOG, docstrings, comments,
messages and our own identifiers. That is `-our` (colour, behaviour), `-re` (centre),
`-ize`/`-yze` (organize, analyze, normalize), a doubled `l` (modelled, labelled), `-ence`
(defence), *licence* as a noun and *license* as a verb, and **artifact**. Not changed:
third-party text kept verbatim (the Contributor Covenant, quoted messages), the keys and
names of external formats (`license` in `pyproject.toml`, the `LICENSE` file), compiler
output and mock data.
`tests/unit/test_spelling.py` flags the British `-ise`/`-yse` and the American
`-or`/`-er`/single-`l`/`-ense` forms; extend its exceptions rather than misspelling to
please it. Issue and PR text follows the same rule.

## Branching

One long-lived branch, `main` (the default branch), plus one branch per v4 milestone
(`m0-foundation`, `m1-model`, …, `m7-docs`, `mb0-action-extraction`) cut from `main`.
MB1 (#132) was folded into MB0, whose action work is done in `jpipe-ci-actions`. Rationale:
[ADR-0014](docs/adr/0014-trunk-with-milestone-branches.md) and
[ADR-0015](docs/adr/0015-draft-pull-request-per-milestone.md); workflow:
[`docs/contributing.md`](docs/contributing.md). There is no `dev` branch any more; v3 is
the `v3.6.0` tag.

- Ticket work goes on its milestone's branch, as one or more commits; the commit that
  completes a ticket ends with `Closes #N`.
- Each milestone has **one** PR into `main`, opened as a **draft** when its branch is first
  pushed (SonarCloud only analyzes `main` and PRs on this plan). An assistant opens it only
  when the maintainer asks; otherwise it pushes the branch and stops.
- **Before a milestone is complete, update [`docs/v4-progress.md`](docs/v4-progress.md)**
  on its branch: set the milestone's row to done (with its issues and ADRs), add a
  subsection under *What v4 can do so far* listing the user-visible features it added
  (what a user can now do, not the modules built), and extend *Gone from v3* if it removed
  anything. This is part of the milestone's work, like the CHANGELOG, and lands in its PR.
  The README only points to that page.
- **Document what the milestone adds, in the milestone** ([ADR-0017](docs/adr/0017-document-in-the-milestone-that-builds-it.md)):
  a user-visible feature gets its page under `docs/` in the milestone's PR (M2:
  `docs/authoring.md`), with its code examples executed by a test. Documentation issues sit
  on the milestone that builds what they describe; M7 only reviews the whole for
  consistency and writes the README, troubleshooting and migration guide.
- **In the same way, bring [`docs/end-to-end.md`](docs/end-to-end.md) up to date.** It
  walks the release example from `.jd` to verdict for human readers (the e2e scenarios are
  for coverage). Turn each stage the milestone built from *planned* into what actually
  happens, quoting output produced by running the code, never written by hand.
  `tests/unit/test_end_to_end_doc.py` keeps its step library, and the validation output it
  quotes, in step with the scenario's.
- The maintainer marks the PR ready for review when the milestone is complete, and merges it.
- Never commit or push to `main` directly.

## Release Process

### Release policy (for automated assistants)

- **Never push a git tag automatically.** Tag creation/push is performed by a
  human maintainer only — it triggers the immutable PyPI/PPA/Homebrew publish.
- **Never open a PR unless the maintainer asks, and never merge one.** Milestone PRs are
  drafts from the start of the milestone (ADR-0015) and are merged by a human. A release
  has no PR of its own.
- **Always maintain `CHANGELOG.md`.** Every release (and notable change) gets an
  entry under a `## [x.y.z] - YYYY-MM-DD` heading, following Keep a Changelog.
- An assistant's scope for a release ends at committing/pushing the prep work
  (version bump + `CHANGELOG.md` + docs) as the last commit of the milestone branch
  being released; the PR, merge, and tag are manual.

**Cutting a release (manual steps):**

1. Set `version` in `pyproject.toml` (only place it's defined; `setup.py` + docs
   derive from it). Use SemVer. Between releases it is a PEP 440 dev version
   (`X.Y.Z.dev0`; `4.0.0.dev0` during the v4 rewrite) that `validate-version` refuses to
   tag; a release replaces it with `X.Y.Z` (or `X.Y.ZaN` / `X.Y.ZrcN`). Write it in canonical form: the
   version tests compare the installed (normalized) version to the raw string.
2. Update `CHANGELOG.md` with a new `## [x.y.z] - YYYY-MM-DD` section.
3. Land both on `main` (last commit of the released milestone, or a maintainer
   commit on `main`); wait for CI.
4. Tag that `main` commit `vX.Y.Z` (must match `pyproject.toml`) and push it.

Pushing the tag triggers `.github/workflows/release.yml` — the tag's version must
match `pyproject.toml`. The pipeline is modelled on the sibling `jpipe-compiler`:
a small set of build jobs feed several **decoupled** publish jobs (a flaky PPA
upload no longer blocks PyPI/Homebrew). Job graph:

- `validate-version` → checks tag format + `pyproject.toml` sync; outputs
  `version`/`tag`/`prerelease` (anything not a bare `X.Y.Z` is a pre-release).
- `test` → `build-python-package` (wheel + sdist).
- `github-release` → GitHub Release with wheel + sdist (binary `.deb`s are built
  by Launchpad, not attached here).
- `publish-pypi` → PyPI via trusted publisher (runs for pre-releases too).
- `publish-ppa` → **`strategy.matrix` over `[noble, resolute, stonking]`** (the two
  most recent LTS plus the current dev series);
  each series builds a signed source package from the committed `debian/` dir and
  `dput`s it to Launchpad. Skipped for pre-releases. (jammy/22.04 is excluded: it
  ships Python 3.10, but the project requires `>=3.11`. `debian/control` enforces this
  via `X-Python3-Version: >= 3.11`.)
- `build-homebrew-formula` + `publish-homebrew` → update the `homebrew-mcscert`
  tap. Skipped for pre-releases.

The Ubuntu series list lives **only** in the `publish-ppa` matrix. Shared
Python/Poetry/graphviz setup is a composite action at
`.github/actions/setup-python-env` (reused by `ci.yml`).

## Backlog

The v4 plan lives in the GitHub issues #107–#133 (milestones M0–M7, MB0, MB1). #153,
running only the evidence a change affects, has no milestone and three design questions
to settle first. The v3 known-bugs and tech-debt lists were dropped with the v3 code.

## Notes for Maintainers

- **Poetry installation**: install via `pipx` (not Homebrew) to get a clean isolated environment:
  ```bash
  pipx install poetry
  pipx inject poetry poetry-plugin-export
  ```
  Homebrew's Poetry leaks system packages (e.g. `tbb`) into its resolver, breaking plugin installs.

- **Graphviz system dependency**: diagrams are rendered by piping DOT text to the `dot` binary, as the jPipe compiler does (ADR-0022); there is no Python Graphviz package. Only the Graphviz binary is needed, no C headers. On macOS: `brew install graphviz`. On Linux: `sudo apt-get install graphviz`.

- **Debian packaging** lives in the committed `debian/` directory (`3.0 (native)`
  source format, pybuild via `debian/rules`). `setup.py` is the setuptools shim
  pybuild builds from — `debian/rules` pins `PYBUILD_SYSTEM=distutils` so the build
  ignores the poetry-core backend in `pyproject.toml`. There is no longer any
  stdeb/`build-deb.sh`/`stdeb.cfg`; runtime Debian deps are declared in
  `debian/control`. To test locally: `dch --newversion X.Y.Z~jammy1 --distribution
  jammy` then `dpkg-buildpackage -S -us -uc` (source) or `-b` (binary).
- **Runtime dependencies are `>=floor,<cap` ranges** (ADR-0026): the floor is the oldest
  version a supported Ubuntu series ships, and `debian/control` declares the same floors
  (`tests/unit/test_dependency_policy.py` checks both). CI's `test` job installs exactly
  `poetry.lock` (the setup action never runs `poetry lock`: commit the lock file with any
  change to `pyproject.toml`), and `test-floor` runs the suite on the floors, on Python
  3.12. Dependabot updates the lock file weekly, never a floor or a cap: a major is a
  branch of its own. Raise a floor when a supported series stops shipping it.
- Python is `>=3.11`: `test` runs on 3.11, `test-floor` on 3.12.
