# jPipe Runner

The jPipe Runner makes a [jPipe](https://www.jpipe.org) justification executable. You
bind each element of the argument to a Python function. The runner checks that the
argument and the code agree, runs the checks in dependency order, and reports which
claims hold.

> [!IMPORTANT]
> **v4 is being rewritten from scratch on `main`, and nothing on `main` runs yet.**
> The current release is **3.6.0**, the last of v3, and the commands under
> [Install](#install) give you that. Why v4 is a rewrite, not a refactor:
> [ADR-0002](docs/adr/0002-rewrite-from-scratch.md). Progress: [Status](#status).

## How it works

```text
release.jd ── jpipe process -f JSON ──▶ release.json ──┐
                                                       ├──▶ jpipe-runner ──▶ report + diagram
steps.py  (one Python function per element) ───────────┘
```

1. The [jPipe compiler](https://github.com/jpipe-mcscert/jpipe-compiler) compiles a
   `.jd` model to JSON. The runner never parses `.jd` itself
   ([ADR-0001](docs/adr/0001-consume-compiler-json.md)).
2. A *step library* implements the argument: each evidence and strategy is a decorated
   Python function that declares the values it consumes and produces.
3. The runner validates the pair, executes the steps in topological order, and reports
   a status for every element, in text or JSON, with a Graphviz diagram.

## Install

These commands install **3.6.0**. You need Python 3.11 or later and, for diagrams, the
[Graphviz](https://graphviz.org/download/) `dot` binary. The package managers install
both for you.

| Platform | Command |
|----------|---------|
| macOS (Homebrew) | `brew tap jpipe-mcscert/mcscert && brew install jpipe-runner` |
| Ubuntu (APT) | `sudo add-apt-repository ppa:mcscert/ppa && sudo apt install jpipe-runner` |
| Anywhere (pip) | `pip install jpipe-runner` |

Once 4.0.0 is released, these commands install v4. To keep v3, pin it:
`pip install jpipe-runner==3.6.0` or `brew install jpipe-runner@3.6.0`.

**Using v3:** follow the [jPipe tutorials](https://www.jpipe.org/tutorials/runner/). The v3
reference documentation is kept at the
[`v3.6.0` tag](https://github.com/jpipe-mcscert/jpipe-runner/tree/v3.6.0/docs).

## What v4 will look like

The design is settled in the v4 issues, but none of it is implemented yet. It may still
change before 4.0.0.

**Authoring.** There is one decorator per element kind. The binding ids are positional,
and a step returns its outcome instead of calling a `produce` callback
([#113](https://github.com/jpipe-mcscert/jpipe-runner/issues/113),
[#114](https://github.com/jpipe-mcscert/jpipe-runner/issues/114)):

```python
from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy


@evidence("release:e1", produces=["tests_pass"])
def the_test_suite_passes() -> Outcome:
    if Path("mock/tests.ok").is_file():
        return Pass(tests_pass=True)
    return Fail("mock/tests.ok not found")


@strategy("release:s", consumes=["tests_pass", "changelog_ok"])
def all_release_gates_pass(tests_pass: bool, changelog_ok: bool) -> Outcome:
    return Pass() if tests_pass and changelog_ok else Fail("a release gate did not pass")
```

**Running** ([#124](https://github.com/jpipe-mcscert/jpipe-runner/issues/124)):

```bash
jpipe process -i release.jd -m release -f JSON -o release.json
jpipe-runner --library steps.py --report json release.json
```

The exit code tells a CI script what happened: `0` the justification holds, `1` it does
not, `2` usage error, `3` validation failed, `4` I/O error.

**Breaking changes from v3:**

| v3 | v4 |
|----|----|
| `@jpipe(consume=…, produce=…)` with `@jpipe_link` | `@evidence`, `@strategy`, `@sub_conclusion`, `@conclusion`, each taking its ids |
| a `produce(name, value)` parameter; return `True`/`False` | return `Pass(...)`, `Fail(reason)` or `Skip(reason)` |
| `@skip` (decided at import time) | `return Skip(reason)` (decided at run time) |
| `--variable`, `--config-file` | removed: a step reads its inputs from the world |
| `--diagram` (parsed, never used) | removed |
| any warning fails the run | warnings are reported and the run continues; `--strict` makes them errors |
| a decorator id matching no element is ignored silently | an error (JP015) |
| text output only | a versioned JSON report, the contract for CI and the GitHub Action |

The jPipe compiler's `-f PYTHON` export still generates v3 step libraries. It will be
updated for 4.0.0.

## Status

The rewrite is tracked as GitHub
[milestones](https://github.com/jpipe-mcscert/jpipe-runner/milestones). Each one is
developed on its own branch, with a single pull request
([ADR-0014](docs/adr/0014-trunk-with-milestone-branches.md)).

| Milestone | Scope |
|-----------|-------|
| **M0 Foundation** | tooling, quality gate, ADRs, test architecture (in review: [#138](https://github.com/jpipe-mcscert/jpipe-runner/pull/138)) |
| M1 Model | the justification model and its JSON loader |
| M2 Authoring API | decorators, outcomes, binding resolution |
| M3 Validation | the rule framework and its 16 rules |
| M4 Execution | the engine and the step-library loader |
| M5 Reporting | the run report, the JSON contract, diagrams |
| M6 CLI | the command line, exit codes, logging |
| M7 Docs | tutorial, authoring guide, CLI and report reference |
| MB0, MB1 | moving the GitHub Action to `jpipe-runner-action` and rewriting it on the JSON report |

## Development

You need Python 3.11 or later, [Poetry](https://python-poetry.org) (install it with
`pipx install poetry`), and the Graphviz `dot` binary.

```bash
poetry install
poetry run pytest                  # all tests, with coverage
poetry run pytest -m unit          # tests/unit/ only
poetry run pytest -m e2e           # tests/e2e/ only
poetry run ruff check . && poetry run ruff format --check .
poetry run mypy                    # --strict, over src/
pre-commit install                 # run ruff and mypy before each commit
```

- [`tests/README.md`](tests/README.md) describes the test architecture: rule tests,
  golden reports, property tests.
- Every pull request goes through the SonarCloud quality gate
  ([ADR-0004](docs/adr/0004-sonarcloud-quality-gate.md)).
- [`docs/contributing.md`](docs/contributing.md) covers branches, pull requests and
  releases.
- [`docs/adr/`](docs/adr/README.md) records the design decisions and why they were made.
- [`CHANGELOG.md`](CHANGELOG.md) lists what changed in each release.

## License

MIT. See [LICENSE](LICENSE).

## Authors

* [Jason Lyu](https://github.com/xjasonlyu)
* [Baptiste Lacroix](https://github.com/BaptisteLacroix)
* [Sébastien Mosser](https://github.com/mosser)
* [Corentin Veillard](https://github.com/corentinVei)

## How to cite

```bibtex
@software{mcscert:jpipe-runner,
  author = {Mosser, Sébastien and Lyu, Jason and Lacroix, Baptiste and Veillard, Corentin},
  license = {MIT},
  title = {{jPipe Runner}},
  url = {https://github.com/jpipe-mcscert/jpipe-runner}
}
```

## Contact

If you are interested in the research behind jPipe, contact the principal investigator,
[Dr. Sébastien Mosser](mailto:mossers@mcmaster.ca).
