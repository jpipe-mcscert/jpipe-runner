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
                         [--verbose] [--config-file PATH] [--gui] jd_file
```

**Key options:**

* `--variable`, `-v`: Define `NAME:VALUE` pairs for template variables.
* `--library`, `-l`: Load additional Python modules (steps).
* `--diagram`, `-d`: Select diagrams by wildcard pattern.
* `--output`, `-o`: Specify output image file (format inferred by extension).
* `--dry-run`: Validate workflow without executing.
* `--verbose`, `-V`: Enable debug logging.
* `--config-file`: Load workflow config from a YAML file.
* `--gui`: Launch the Tkinter-based `GraphWorkflowVisualizer`

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
* Optional for GUI version: [Tkinter](https://docs.python.org/3/library/tkinter.html)

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

## 📚 Learn More

* [Usage Guide](docs/USAGE.md)
* [Packaging & CI/CD](docs/PACKAGING_RELEASE.md)
* [Troubleshooting](docs/TROUBLESHOOTING.md)
* [Developer Docs (Sphinx)](docs/BUILD_DOCS.md)
* [Contributing](docs/CONTRIBUTING.md)

## 📄 License

MIT License — see [LICENSE](LICENSE).

## 👤 Authors

* [Jason Lyu](https://github.com/xjasonlyu)
* [Baptiste Lacroix](https://github.com/BaptisteLacroix)
* [Sébastien Mosser](https://github.com/mosser)

## How to cite?

```bibtex
@software{mcscert:jpipe-runner,
  author = {Mosser, Sébastien and Lyu, Jason and Lacroix, Baptiste},
  license = {MIT},
  title = {{jPipe Runner}},
  url = {https://github.com/ace-design/jpipe-runner}
}
```

## Contact Us

If you're interested in contributing to the research effort related to jPipe projects, feel free to contact the PI:

- [Dr. Sébastien Mosser](mailto:mossers@mcmaster.ca)
