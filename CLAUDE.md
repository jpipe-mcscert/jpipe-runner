# jpipe-runner — Project Guide for Claude

## Project Overview

`jpipe-runner` is a **Python CLI tool and GitHub Action** (v3.5.0) that orchestrates *justification pipelines* — research workflows where Python functions explicitly declare the variables they produce and consume. It validates dependency graphs, executes them in topological order, and can visualise results.

- **Language**: Python ≥ 3.11
- **Build tool**: Poetry
- **License**: MIT
- **Distribution**: PyPI, Ubuntu PPA (Launchpad), Homebrew, GitHub Releases
- **Upstream**: `jpipe-mcscert/jpipe-runner`

## Architecture

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
| `pyproject.toml` | Dependencies, entry points, optional extras (`docs`, `full`) |
| `.github/workflows/ci.yml` | CI — pytest on push to `main` |
| `.github/workflows/release.yml` | Multi-stage release pipeline (see Release section) |

## Testing

```bash
poetry install
poetry run pytest -m unit    # unit tests only
poetry run pytest -m e2e     # end-to-end (subprocess CLI invocations)
poetry run pytest            # all tests
```

Test layout:
- `tests/unit/` — engine, context, decorators, validators, structure normalisation
- `tests/e2e/` — full CLI invocations covering success, exceptions, circular deps, missing producers/consumers, self-deps, skip scenarios

Coverage metrics are configured via `pytest-cov` (see `pyproject.toml` and `pytest.ini`).

## Release Process

### Release policy (for automated assistants)

- **Never push a git tag automatically.** Tag creation/push is performed by a
  human maintainer only — it triggers the immutable PyPI/PPA/Homebrew publish.
- **Never open or merge a PR automatically.** The `dev → main` release PR is
  opened and merged by a human.
- **Always maintain `CHANGELOG.md`.** Every release (and notable change) gets an
  entry under a `## [x.y.z] - YYYY-MM-DD` heading, following Keep a Changelog.
- An assistant's scope for a release ends at committing/pushing the prep work to
  `dev` (version bump + `CHANGELOG.md` + docs); the PR, merge, and tag are manual.

**Cutting a release (manual steps):**

1. Bump `version` in `pyproject.toml` (only place it's defined; `setup.py` + docs
   derive from it). Use SemVer.
2. Update `CHANGELOG.md` with a new `## [x.y.z] - YYYY-MM-DD` section.
3. Open a PR `dev → main`; merge once CI passes.
4. Tag the merged `main` commit `vX.Y.Z` (must match `pyproject.toml`) and push it.

Pushing the tag triggers `.github/workflows/release.yml` — the tag's version must
match `pyproject.toml`. The pipeline is modelled on the sibling `jpipe-compiler`:
a small set of build jobs feed several **decoupled** publish jobs (a flaky PPA
upload no longer blocks PyPI/Homebrew/docs). Job graph:

- `validate-version` → checks tag format + `pyproject.toml` sync; outputs
  `version`/`tag`/`prerelease` (anything not a bare `X.Y.Z` is a pre-release).
- `test` → `build-python-package` (wheel + sdist) and `build-docs` (Sphinx).
- `github-release` → GitHub Release with wheel + sdist (binary `.deb`s are built
  by Launchpad, not attached here).
- `publish-pypi` → PyPI via trusted publisher (runs for pre-releases too).
- `publish-ppa` → **`strategy.matrix` over `[noble, questing, resolute]`**;
  each series builds a signed source package from the committed `debian/` dir and
  `dput`s it to Launchpad. Skipped for pre-releases. (jammy/22.04 is excluded: it
  ships Python 3.10, but the project requires `>=3.11` — `networkx 3.5` won't even
  install on 3.10. `debian/control` enforces this via `X-Python3-Version: >= 3.11`.)
- `build-homebrew-formula` + `publish-homebrew` → update the `homebrew-mcscert`
  tap. Skipped for pre-releases.
- `deploy-docs` → GitHub Pages.

The Ubuntu series list lives **only** in the `publish-ppa` matrix. Shared
Python/Poetry/graphviz setup is a composite action at
`.github/actions/setup-python-env` (reused by `ci.yml`).

## Known Bugs

~~`framework/logger.py:35` — `has_errors()` always returns `True`~~ **Fixed in `refactor` branch** (commit `b0500d8`). Operator precedence bug: `"ERROR" or "WARNING"` short-circuited to a truthy string. Fix: `any("ERROR" in log or "WARNING" in log for log in self.logs)`. Tests added in `tests/unit/test_logger.py`.

## Tech Debt Backlog (prioritised)

1. **Add linting/formatting** — configure `ruff` (or black + flake8) via pre-commit hooks
2. **Add coverage.py** — configure in `pyproject.toml` and add CI coverage gate
3. **Simplify `setup.py`** — replace the 500+ LOC custom TOML parser with `tomllib` (stdlib ≥ 3.11)
4. **Refactor `engine.py`** — break `justify()` and `export_to_format()` (>200 LOC each) into smaller methods
5. **Add type hints** — particularly in validators and decorators (`Any` overused)
6. **Thread-safety documentation** — document global `ctx` singleton limitations in context.py docstring

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
