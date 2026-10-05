# jpipe-runner — Project Guide for Claude

## Project Overview

`jpipe-runner` is a **Python CLI tool and GitHub Action** (v3.5.0) that orchestrates *justification pipelines* — research workflows where Python functions explicitly declare the variables they produce and consume. It validates dependency graphs, executes them in topological order, and can visualise results.

- **Language**: Python ≥ 3.11
- **Build tool**: Poetry
- **License**: MIT
- **Distribution**: PyPI, Ubuntu PPA (Launchpad), Homebrew, GitHub Releases
- **Upstream**: `jpipe-mcscert/jpipe-runner`

## Architecture

> **v3, for reference only.** `src/` and `tests/` were deleted for the v4 rewrite (#107);
> this section and *Critical Files* describe v3 as it is at the `v3.6.0` tag
> (`git show v3.6.0:<path>`). They are rewritten for v4 in #129.

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
- The `unit` / `e2e` markers are applied by `tests/conftest.py` from the test's directory.
  A test file outside `tests/unit/` or `tests/e2e/` is a collection error.
- `pre-commit install` runs ruff and mypy before each commit; CI's `lint` job runs the same.
- The quality gate is SonarCloud (`sonar-project.properties`, `.github/workflows/sonar.yml`,
  [ADR-0004](docs/adr/0004-sonarcloud-quality-gate.md)); it reads the `coverage.xml` pytest writes.

## Branching

One long-lived branch, `main` (the default branch), plus one branch per v4 milestone
(`m0-foundation`, `m1-model`, …, `m7-docs`, `mb0-action-extraction`) cut from `main`.
MB1 (#132) is done in the `jpipe-runner-action` repository and has no branch here. Rationale:
[ADR-0014](docs/adr/0014-trunk-with-milestone-branches.md); workflow:
[`docs/contributing.md`](docs/contributing.md). There is no `dev` branch any more; v3 is
the `v3.6.0` tag.

- Ticket work goes on its milestone's branch, as one or more commits; the commit that
  completes a ticket ends with `Closes #N`.
- An assistant pushes the milestone branch and stops. The maintainer opens **one** PR
  per milestone into `main` and merges it.
- Never commit or push to `main` directly.

## Release Process

### Release policy (for automated assistants)

- **Never push a git tag automatically.** Tag creation/push is performed by a
  human maintainer only — it triggers the immutable PyPI/PPA/Homebrew publish.
- **Never open or merge a PR automatically.** Milestone PRs are opened and merged
  by a human. A release has no PR of its own.
- **Always maintain `CHANGELOG.md`.** Every release (and notable change) gets an
  entry under a `## [x.y.z] - YYYY-MM-DD` heading, following Keep a Changelog.
- An assistant's scope for a release ends at committing/pushing the prep work
  (version bump + `CHANGELOG.md` + docs) as the last commit of the milestone branch
  being released; the PR, merge, and tag are manual.

**Cutting a release (manual steps):**

1. Bump `version` in `pyproject.toml` (only place it's defined; `setup.py` + docs
   derive from it). Use SemVer.
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
