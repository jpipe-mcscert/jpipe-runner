# jPipe Runner

```text
     _ ____  _              ____                              
   (_)  _ \(_)_ __   ___   |  _ \ _   _ _ __  _ __   ___ _ __ 
   | | |_) | | '_ \ / _ \  | |_) | | | | '_ \| '_ \ / _ \ '__|
   | |  __/| | |_) |  __/  |  _ <| |_| | | | | | | |  __/ |   
  _/ |_|   |_| .__/ \___|  |_| \_\\__,_|_| |_|_| |_|\___|_|   
 |__/        |_|                                              
```

A Justification Runner designed for jPipe.

## 🚀 Usage

### CLI

```bash
poetry run jpipe-runner [-h] [--variable NAME:VALUE] [--library LIB] \
                         [--diagram PATTERN] [--output FILE] [--dry-run] \
                         [--quiet] [--verbose] [--config-file PATH] jd_file
```

**Key options:**

* `--variable`, `-v`: Define `NAME:VALUE` pairs for template variables.
* `--library`, `-l`: Load additional Python modules (steps).
* `--diagram`, `-d`: Select diagrams by wildcard pattern.
* `--output`, `-o`: Specify output image file (format inferred by extension).
* `--dry-run`: Validate workflow without executing.
* `--quiet`, `-q`: Suppress startup and exception ASCII banners.
* `--verbose`, `-V`: Enable debug logging.
* `--config-file`: Load workflow config from a YAML file.
Example:

```bash
poetry run jpipe-runner --variable X:10 --diagram "flow*" \
                         --output diagram.png workflow.jd
```

For detailed instructions on how to execute the project, including descriptions of all CLI parameters and usage examples, see the [Usage Guide](docs/USAGE.md).

## ⚙️Installation

### Prerequisites

* Python 3.10+
* [Poetry](https://python-poetry.org)
* [Graphviz](https://graphviz.org/) (`libgraphviz-dev`, `pkg-config`)

### From Source

```bash
# Lock and install dependencies
poetry lock
poetry install
```

### Build Package

```bash
# Run tests
poetry run pytest

# Build distributable
poetry build
```

## 🏷️ Releasing

Releases are tags on `main`, published automatically when the tag is pushed. A
release needs no pull request of its own (see
[ADR-0014](docs/adr/0014-trunk-with-milestone-branches.md)). See
[`CHANGELOG.md`](CHANGELOG.md) for the release history.

1. **Bump the version** in `pyproject.toml` (single source of truth — `setup.py`
   and the docs derive from it). Follow [SemVer](https://semver.org): patch for
   fixes, minor for backward-compatible features, major for breaking changes.
2. **Update `CHANGELOG.md`** — move the relevant notes under a new
   `## [x.y.z] - YYYY-MM-DD` heading.
3. **Land both on `main`**, either as the last commit of the milestone being
   released or as a commit directly on `main`, and wait for CI to go green.
4. **Tag that commit** on `main` and push the tag:
   ```bash
   git checkout main && git pull
   git tag vX.Y.Z          # must equal the pyproject.toml version
   git push origin vX.Y.Z
   ```

Pushing the `vX.Y.Z` tag triggers the release pipeline
([`.github/workflows/release.yml`](.github/workflows/release.yml)), which
validates the tag/version match, runs the tests, builds the docs, wheel, sdist
and signed `.deb`, then publishes to **GitHub Releases**, **PyPI**, the **Ubuntu
PPA**, and the **Homebrew** tap, and deploys the docs to GitHub Pages.

> The tag version **must** match `pyproject.toml` exactly, or the pipeline fails
> at the `validate-version` step.

## 📚 Learn More

* [Usage Guide](docs/USAGE.md)
* [Releasing](#-releasing) · [Changelog](CHANGELOG.md)
* [Packaging & CI/CD](docs/PACKAGING_RELEASE.md)
* [Troubleshooting](docs/TROUBLESHOOTING.md)
* [Developer Docs (Sphinx)](docs/BUILD_DOCS.md)
* [Contributing](docs/contributing.md)

## 📄 License

MIT License — see [LICENSE](LICENSE).

## 👤 Authors

* [Jason Lyu](https://github.com/xjasonlyu)
* [Baptiste Lacroix](https://github.com/BaptisteLacroix)
* [Sébastien Mosser](https://github.com/mosser)
* [Corentin Veillard](https://github.com/corentinVei)

## How to cite?

```bibtex
@software{mcscert:jpipe-runner,
  author = {Mosser, Sébastien and Lyu, Jason and Lacroix, Baptiste, and Corentin Veillard},
  license = {MIT},
  title = {{jPipe Runner}},
  url = {https://github.com/ace-design/jpipe-runner}
}
```

## Contact Us

If you're interested in contributing to the research effort related to jPipe projects, feel free to contact the PI:

- [Dr. Sébastien Mosser](mailto:mossers@mcmaster.ca)
