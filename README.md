# jPipe Runner

jPipe Runner checks [jPipe](https://www.jpipe.org) justifications by running them. A
justification argues that a claim holds, such as "version 2.0 is ready to ship", from
evidence and the reasoning that connects it. The runner binds each piece of evidence and
each step of reasoning to a Python function, calls them in order, and reports which claims
hold, for a person at a terminal or for a CI pipeline.

> [!NOTE]
> **Version 4 is not released yet.** This branch holds version 4, a rewrite whose
> [documentation](https://github.com/jpipe-mcscert/jpipe-runner/tree/main/docs) is under
> `docs/`. The [latest stable release](https://github.com/jpipe-mcscert/jpipe-runner/releases/latest)
> is 3.6.0, documented at the
> [`v3.6.0` tag](https://github.com/jpipe-mcscert/jpipe-runner/tree/v3.6.0).

## Install

jPipe Runner needs Python 3.11 or later. Install it in your project's virtual environment,
beside the packages your checks import:

```shell
pip install git+https://github.com/jpipe-mcscert/jpipe-runner
```

Once 4.0.0 is released, `pip install jpipe-runner` will install it, and so will Homebrew
(`brew tap jpipe-mcscert/mcscert && brew install jpipe-runner`) and the Ubuntu PPA
(`sudo add-apt-repository ppa:mcscert/ppa && sudo apt install jpipe-runner`), for checks
that only use Python's standard library. Drawing diagrams also needs
[Graphviz](https://graphviz.org/download/)'s `dot` program.

## In 60 seconds

The [release argument](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/tutorial.md)
rests on two pieces of evidence, a passing test suite and an up-to-date changelog, and on
a strategy that judges them. Compiled by jPipe to `justification.json`, it is checked by a
Python step library, `steps.py`, with one function for each:

```python
from pathlib import Path
from xml.etree import ElementTree

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

RELEASE = "2.0"


@evidence("release:e1", observes={"report": "mock/junit.xml"}, produces=["tests_pass"])
def the_test_suite_passes(report: Path) -> Outcome:
    """[evidence] The test suite passes"""
    suite = ElementTree.parse(report).getroot()
    failed = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
    if failed == 0:
        return Pass(tests_pass=True)
    return Fail(f"{report}: {failed} tests failed")


@evidence("release:e2", observes={"changelog": "mock/CHANGELOG.md"}, produces=["changelog_ok"])
def the_changelog_is_up_to_date(changelog: Path) -> Outcome:
    """[evidence] The changelog is up to date"""
    if RELEASE in changelog.read_text(encoding="utf-8"):
        return Pass(changelog_ok=True)
    return Fail(f"{changelog} does not name release {RELEASE}")


@strategy("release:s", consumes=["tests_pass", "changelog_ok"])
def all_release_gates_pass(tests_pass: bool, changelog_ok: bool) -> Outcome:
    """[strategy] All release gates pass"""
    if tests_pass and changelog_ok:
        return Pass()
    return Fail("a release gate did not pass")
```

Each evidence declares the file it reads and the value it produces; the strategy consumes
both values. Run the argument against the library:

```console
$ jpipe-runner --library steps.py justification.json
Justification: release
  Version 2.0 is ready to ship

  ✔ Evidence    The test suite passes         # release:e1
  ✔ Evidence    The changelog is up to date   # release:e2
  ✔ Strategy    All release gates pass        # release:s
  ✔ Conclusion  Version 2.0 is ready to ship  # release:c

4 elements (4 passed)
verdict: pass
$ echo $?
0
```

Every check passed, so the claim holds, and the exit code is 0. Had the test report
recorded a failure, the evidence would fail, the strategy and the conclusion above it
would be skipped, and the exit code would be 1. `--report report.json` writes the same run
as JSON for programs, and `--diagram release.svg` draws it.

For GitHub Actions, an action that runs a justification on every pull request, and
comments with what holds and what does not, is built in [`jpipe-ci-actions`](https://github.com/jpipe-mcscert/jpipe-ci-actions). Its
first release is pending.

## Documentation

- [Tutorial](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/tutorial.md):
  from a `.jd` file to a green run, every file on one page.
- [Writing a step library](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/authoring.md),
  [the command line](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/cli.md),
  [diagnostic codes](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/rules.md)
  and [the JSON report](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/report-schema.md).
- [Troubleshooting](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/troubleshooting.md),
  and [migrating from v3](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/migration-v3-v4.md).
- [Every page, in reading order](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/README.md).

## Contributing

[`docs/contributing.md`](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/docs/contributing.md)
explains how to set up a development environment, run the tests, and propose a change.

## Authors

* [Jason Lyu](https://github.com/xjasonlyu)
* [Baptiste Lacroix](https://github.com/BaptisteLacroix)
* [Sébastien Mosser](https://github.com/mosser)
* [Corentin Veillard](https://github.com/corentinVei)

## Licence

MIT. See [LICENSE](https://github.com/jpipe-mcscert/jpipe-runner/blob/main/LICENSE).

## How to cite

```bibtex
@software{mcscert:jpipe-runner,
  author = {Mosser, Sébastien and Lyu, Jason and Lacroix, Baptiste and Veillard, Corentin},
  license = {MIT},
  title = {{jPipe Runner}},
  url = {https://github.com/jpipe-mcscert/jpipe-runner}
}
```
