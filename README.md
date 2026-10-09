# jPipe Runner

jPipe Runner executes [jPipe](https://www.jpipe.org) justifications: it binds each element
of a justification to a Python function, runs the checks, and reports which claims hold.

> [!WARNING]
> **Work in progress.** This branch holds version 4, a rewrite from scratch that cannot
> run a justification yet. [`docs/v4-progress.md`](docs/v4-progress.md) says what it can
> do so far. For a working runner, use the
> [latest stable release](https://github.com/jpipe-mcscert/jpipe-runner/releases/latest)
> (3.6.0), whose documentation is at the
> [`v3.6.0` tag](https://github.com/jpipe-mcscert/jpipe-runner/tree/v3.6.0).

## Authors

* [Jason Lyu](https://github.com/xjasonlyu)
* [Baptiste Lacroix](https://github.com/BaptisteLacroix)
* [Sébastien Mosser](https://github.com/mosser)
* [Corentin Veillard](https://github.com/corentinVei)

## Install

| Platform | Command |
|----------|---------|
| macOS (Homebrew) | `brew tap jpipe-mcscert/mcscert && brew install jpipe-runner` |
| Ubuntu (APT) | `sudo add-apt-repository ppa:mcscert/ppa && sudo apt install jpipe-runner` |
| Anywhere (pip) | `pip install jpipe-runner` |

These install the latest stable release. To build from source, see
[Development setup](#development-setup).

## Development setup

You need:

* **Python 3.11 or later.** CI tests on 3.11.
* **[Poetry](https://python-poetry.org) 2.x**, installed with [pipx](https://pipx.pypa.io):
  `pipx install poetry`. Avoid Homebrew's Poetry, which leaks system packages into its
  resolver.
* **[pre-commit](https://pre-commit.com)**, to run the linters before each commit:
  `pipx install pre-commit`.
* **The [Graphviz](https://graphviz.org/download/) `dot` binary**, to render diagrams
  (`brew install graphviz` or `sudo apt-get install graphviz`). The tests that render an
  image are skipped without it.

Clone the repository and set up the environment:

```bash
git clone https://github.com/jpipe-mcscert/jpipe-runner.git
cd jpipe-runner
poetry env use python3.11   # only if `python3` on your PATH is older than 3.11
poetry install              # virtual environment with the runner (editable) and the dev tools
pre-commit install          # run ruff and mypy before each commit
```

Check that everything works by running what CI runs:

```bash
poetry run pytest                  # all tests, with coverage (writes coverage.xml)
poetry run pytest -m unit          # unit tests only
poetry run pytest -m e2e           # end-to-end tests only
poetry run ruff check .            # lint (add --fix to apply the safe fixes)
poetry run ruff format --check .   # formatting (drop --check to reformat)
poetry run mypy                    # type-check src/ in strict mode
```

Run the tools through `poetry run`, so that they use the project's environment and the
editable install of `src/`, not another `jpipe-runner` installed elsewhere. Their
configuration lives in [`pyproject.toml`](pyproject.toml).

## Contributing

[`docs/contributing.md`](docs/contributing.md) explains how to contribute: branches, pull
requests and releases. [`docs/design.md`](docs/design.md) describes how the runner is built,
and [`tests/README.md`](tests/README.md) the test architecture.
Pull requests go through a SonarCloud quality gate
([ADR-0004](docs/adr/0004-sonarcloud-quality-gate.md)).

## Licence

MIT. See [LICENSE](LICENSE).

## How to cite

```bibtex
@software{mcscert:jpipe-runner,
  author = {Mosser, Sébastien and Lyu, Jason and Lacroix, Baptiste and Veillard, Corentin},
  license = {MIT},
  title = {{jPipe Runner}},
  url = {https://github.com/jpipe-mcscert/jpipe-runner}
}
```
