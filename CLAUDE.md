# jpipe-runner — Project Guide for Claude

## Project Overview

`jpipe-runner` is a **Python CLI tool and GitHub Action** (v3.1.0) that orchestrates *justification pipelines* — research workflows where Python functions explicitly declare the variables they produce and consume. It validates dependency graphs, executes them in topological order, and can visualise results.

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
        └─ Output / Viz        Graphviz export, optional Tkinter GUI
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
| `src/jpipe_runner/GraphWorkflowVisualizer.py` | Optional Tkinter GUI (matplotlib extra) |
| `pyproject.toml` | Dependencies, entry points, optional extras (`gui`, `docs`, `full`) |
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

Note: no coverage metrics are configured yet (see tech debt backlog).

## Release Process

Triggered by pushing a `v*.*.*` tag whose version matches `pyproject.toml`. The pipeline:

1. Validates tag format + version sync
2. Runs full test suite
3. Builds Sphinx HTML docs
4. Builds Python wheel + sdist
5. Builds `.deb` packages (base + GUI variant) — GPG-signed
6. Creates GitHub Release with all artifacts
7. Publishes to PyPI (trusted publishers)
8. Uploads to Ubuntu PPA (Launchpad)
9. Updates Homebrew formula in `homebrew-mcscert` tap
10. Deploys docs to GitHub Pages

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

- **Graphviz system dependency**: pygraphviz compiles a C extension — Graphviz headers must be on the compiler path. On macOS with Homebrew:
  ```bash
  brew install graphviz
  export CFLAGS="-I$(brew --prefix graphviz)/include"
  export LDFLAGS="-L$(brew --prefix graphviz)/lib"
  poetry install
  ```
  Add the two `export` lines to `~/.zshrc` to avoid setting them every session.
  On Linux: `sudo apt-get install graphviz libgraphviz-dev pkg-config build-essential python3-dev`.

- The `setup.py` is only needed for Debian packaging (stdeb); Poetry handles everything else.
- GUI extra (`matplotlib`) is distributed as a separate `.deb` package and Homebrew formula.
- Python version is pinned to `>=3.11` in `pyproject.toml` but CI only tests 3.11 — consider matrix testing.
