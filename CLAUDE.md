# jpipe-runner — Project Guide for Claude

## Project Overview

`jpipe-runner` is a **Python CLI tool and GitHub Action** (v4 in development, `4.0.0.dev0`; v3 frozen at 3.6.0) that orchestrates *justification pipelines* — research workflows where Python functions explicitly declare the variables they produce and consume. It validates dependency graphs, executes them in topological order, and can visualize results.

- **Language**: Python ≥ 3.11
- **Build tool**: Poetry
- **Licence**: MIT
- **Distribution**: PyPI, Ubuntu PPA (Launchpad), Homebrew, GitHub Releases
- **Upstream**: `jpipe-mcscert/jpipe-runner`

## Architecture

> **v3, for reference only.** `src/` and `tests/` were deleted for the v4 rewrite (#107);
> this section and *Critical Files* describe v3 as it is at the `v3.6.0` tag
> (`git show v3.6.0:<path>`). They are rewritten for v4 in #129.
>
> **The v4 design is in [`docs/design.md`](docs/design.md)**: a Mermaid module diagram and
> a high-level class diagram (no members). Keep it in step with the code, in the same
> commit: `tests/unit/test_design_doc.py` fails when a module is missing from the module
> diagram, when its solid arrows are not exactly the imports between modules, or when a
> module's public classes differ from its `namespace` in the class diagram. The page itself
> does not mention tests or ADRs.

```
CLI (runner.py:main)
  └─► PipelineEngine          (framework/engine.py — 773 LOC)
        ├─ load_config()       parse JSON workflow + YAML variables
        ├─ validate()          6 Validator classes (validators.py — 674 LOC)
        │     ├─ missing producer / consumer
        │     ├─ circular dependency
        │     ├─ duplicate declarations
        │     └─ ordering
        ├─ RuntimeContext      (context.py — 232 LOC)
        │     └─ global singleton ctx; tracks PRODUCE/CONSUME vars per function
        ├─ PythonRuntime       (runtime.py — 142 LOC) — dynamic module loading
        ├─ Decorators          (framework/decorators/)
        │     ├─ @jpipe        registers produce/consume + injects args via AST
        │     ├─ @skip         conditional skip
        │     └─ @contribution marks contribution nodes
        └─ Output / Viz        Graphviz export
```

Key design choices:
- **NetworkX DiGraph** for topological sort and cycle detection.
- **AST-based variable inspection** (`ConsumedVariableChecker`, `ProducedVariableChecker`) validates actual usage vs. declarations.
- **Global singleton** `ctx` for variable state — simple but not thread-safe.
- **Dry-run mode** supported natively.
- **GitHub Actions log grouping** via env-var detection.

## Critical Files

| File | Purpose |
|------|---------|
| `src/jpipe_runner/runner.py` | CLI entry point, argument parsing, output formatting |
| `src/jpipe_runner/framework/engine.py` | Core execution engine (`PipelineEngine`) |
| `src/jpipe_runner/framework/validators.py` | All 6 pipeline validators |
| `src/jpipe_runner/framework/context.py` | Variable lifecycle (`RuntimeContext` singleton) |
| `src/jpipe_runner/framework/logger.py` | Logging — **contains a known bug** (see below) |
| `src/jpipe_runner/framework/decorators/jpipe_decorator.py` | `@jpipe` decorator + AST checks |
| `src/jpipe_runner/runtime.py` | Dynamic Python module loader |
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
  golden reports of the e2e scenarios.
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
names of external formats (`license` in `pyproject.toml`, GitHub's branding key in
`action.yml`, the `LICENSE` file), compiler output and mock data.
`tests/unit/test_spelling.py` flags the British `-ise`/`-yse` and the American
`-or`/`-er`/single-`l`/`-ense` forms; extend its exceptions rather than misspelling to
please it. Issue and PR text follows the same rule.

## Branching

One long-lived branch, `main` (the default branch), plus one branch per v4 milestone
(`m0-foundation`, `m1-model`, …, `m7-docs`, `mb0-action-extraction`) cut from `main`.
MB1 (#132) is done in the `jpipe-runner-action` repository and has no branch here. Rationale:
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
  `tests/unit/test_end_to_end_doc.py` keeps its step library in step with the scenario's.
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
   (`4.0.0.dev0` during the v4 rewrite) that `validate-version` refuses to tag; a release
   replaces it with `X.Y.Z` (or `X.Y.ZaN` / `X.Y.ZrcN`). Write it in canonical form: the
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
  ships Python 3.10, but the project requires `>=3.11` — `networkx 3.5` won't even
  install on 3.10. `debian/control` enforces this via `X-Python3-Version: >= 3.11`.)
- `build-homebrew-formula` + `publish-homebrew` → update the `homebrew-mcscert`
  tap. Skipped for pre-releases.

The Ubuntu series list lives **only** in the `publish-ppa` matrix. Shared
Python/Poetry/graphviz setup is a composite action at
`.github/actions/setup-python-env` (reused by `ci.yml`).

## Backlog

The v4 plan lives in the GitHub issues #107–#133 (milestones M0–M7, MB0, MB1). The v3
known-bugs and tech-debt lists were dropped with the v3 code.

## Notes for Maintainers

- **Poetry installation**: install via `pipx` (not Homebrew) to get a clean isolated environment:
  ```bash
  pipx install poetry
  pipx inject poetry poetry-plugin-export
  ```
  Homebrew's Poetry leaks system packages (e.g. `tbb`) into its resolver, breaking plugin installs.

- **Graphviz system dependency**: the `graphviz` Python package calls the `dot` binary at runtime — only the Graphviz binary is needed, no C headers. On macOS: `brew install graphviz`. On Linux: `sudo apt-get install graphviz`.

- **Debian packaging** lives in the committed `debian/` directory (`3.0 (native)`
  source format, pybuild via `debian/rules`). `setup.py` is the setuptools shim
  pybuild builds from — `debian/rules` pins `PYBUILD_SYSTEM=distutils` so the build
  ignores the poetry-core backend in `pyproject.toml`. There is no longer any
  stdeb/`build-deb.sh`/`stdeb.cfg`; runtime Debian deps are declared in
  `debian/control`. To test locally: `dch --newversion X.Y.Z~jammy1 --distribution
  jammy` then `dpkg-buildpackage -S -us -uc` (source) or `-b` (binary).
- Python version is pinned to `>=3.11` in `pyproject.toml` but CI only tests 3.11 — consider matrix testing.
