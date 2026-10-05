# jPipe Runner

jPipe Runner executes [jPipe](https://www.jpipe.org) justifications: it binds each element
of a justification to a Python function, runs the checks, and reports which claims hold.

> [!WARNING]
> **Work in progress.** This branch holds version 4, a rewrite from scratch that cannot
> run a justification yet. For a working runner, use the
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

These install the latest stable release.

To build from source, you need Python 3.11 or later and [Poetry](https://python-poetry.org):

```bash
git clone https://github.com/jpipe-mcscert/jpipe-runner.git
cd jpipe-runner
poetry install
```

## Contributing

See [`docs/contributing.md`](docs/contributing.md).

## License

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
