# jPipe Runner

jPipe Runner executes [jPipe](https://www.jpipe.org) justifications. It binds each element
of a justification to a Python function, checks that the argument and the code agree,
runs the checks in dependency order, and reports which claims hold.

This repository holds **version 4**, a rewrite from scratch
([ADR-0002](docs/adr/0002-rewrite-from-scratch.md)). It is under development and cannot
run a justification yet. Published releases up to 3.6.0 belong to the previous line; see
[`CHANGELOG.md`](CHANGELOG.md).

## Status

Implemented so far:

- **The `jpipe_runner` package.** It is installable and typed (`py.typed`), and exposes
  `__version__` only.
- **The test architecture** ([`tests/README.md`](tests/README.md)):
  - `unit` and `e2e` tests, selected by directory;
  - a golden-report harness, which compares a run's whole JSON report with a committed
    file;
  - 14 end-to-end scenarios under `tests/e2e/scenarios/`, each pairing a compiled
    justification with its step library;
  - hypothesis strategies that generate well-formed justification models.
- **The quality tooling**:
  - `ruff` for lint and formatting;
  - `mypy --strict`;
  - `pytest` with coverage;
  - pre-commit hooks;
  - CI on every push;
  - a SonarCloud quality gate on pull requests
    ([ADR-0004](docs/adr/0004-sonarcloud-quality-gate.md)).
- **The release pipeline.** A version tag publishes to GitHub Releases, PyPI, the Ubuntu
  PPA `ppa:mcscert/ppa` and the Homebrew tap `jpipe-mcscert/mcscert`.
- **The design decisions recorded so far**, in [`docs/adr/`](docs/adr/README.md).

The remaining work is tracked as GitHub
[milestones](https://github.com/jpipe-mcscert/jpipe-runner/milestones).

## Repository layout

| Path | Contents |
|------|----------|
| `src/jpipe_runner/` | the package |
| `tests/unit/`, `tests/e2e/` | unit and end-to-end tests; `tests/e2e/scenarios/` holds the scenarios |
| `tests/*.py` | test helpers: golden reports, scenario loading, hypothesis strategies |
| `docs/adr/` | architecture decision records |
| `docs/contributing.md` | branches, pull requests and releases |
| `.github/workflows/` | `ci.yml` (lint, types, tests), `sonar.yml` (quality gate), `release.yml` (publishing), `update-homebrew.yml` (republish a formula) |
| `debian/`, `setup.py`, `Formula/`, `script/` | packaging for the PPA and Homebrew |

## Development

Requirements:

- Python 3.11 or later;
- [Poetry](https://python-poetry.org), installed with `pipx install poetry`;
- the [Graphviz](https://graphviz.org/download/) `dot` binary.

```bash
poetry install                     # set up the environment
poetry run pytest                  # all tests, with coverage (writes coverage.xml)
poetry run pytest -m unit          # unit tests only
poetry run pytest -m e2e           # end-to-end tests only
poetry run ruff check .            # lint
poetry run ruff format --check .   # formatting
poetry run mypy                    # type-check src/ in strict mode
pre-commit install                 # run ruff and mypy before each commit
```

The end-to-end scenarios are skipped until the command-line interface exists.

## Contributing

Work happens on one branch per milestone, each with a single pull request into `main`.
Read [`docs/contributing.md`](docs/contributing.md) before opening one.

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

For the research behind jPipe, contact the principal investigator,
[Dr. Sébastien Mosser](mailto:mossers@mcmaster.ca).
