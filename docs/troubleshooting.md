# Troubleshooting

Each entry starts from what you see, says why, and what to do. The sessions run the
[release example](end-to-end.md); [`rules.md`](rules.md) explains every diagnostic code,
and [`cli.md`](cli.md#exit-codes) every exit code.

## Installing

### Version 3 runs instead of version 4

Version 3's API and options are not the ones this documentation describes.
`jpipe-runner --version` says which one runs; version 3 has no `--version` option, and
reports a usage error. Version 3 may still be installed, or pinned (`jpipe-runner<4` in a
requirements file), or an older `jpipe-runner` may come first on the `PATH`. Upgrade it in
the environment that runs it (`pip install -U jpipe-runner`, `brew upgrade jpipe-runner`,
or `sudo apt upgrade jpipe-runner`), and check `which jpipe-runner`.

### pip refuses to install it

jpipe-runner needs Python 3.11 or later. On an older Python, pip finds no version it can
install. Create the virtual environment with a newer Python (`python3.11 -m venv .venv`).

### A diagram needs Graphviz

Every diagram format but `dot` is drawn by Graphviz's `dot` program. Without it, the
command stops before any step runs:

```console
$ jpipe-runner --library steps.py --diagram release.svg justification.json
jpipe-runner: error: Graphviz's dot is needed to draw release.svg, and is not installed or not on the PATH: install Graphviz (https://graphviz.org/download/), or draw a .dot file
$ echo $?
4
```

Install Graphviz (`brew install graphviz`, `sudo apt-get install graphviz`, or from
<https://graphviz.org/download/>), and check that `dot -V` works in the same shell. Only
the program is needed: no Python package, and no C headers. Or draw a `.dot` file, which
needs nothing, and render it elsewhere.

## Step libraries

### A step library cannot import a module

A step library is imported by the Python that runs jpipe-runner, and only finds what that
Python can import. Here the library imports `release_checks`, a module of its own, kept in
`checks/`:

```console
$ jpipe-runner --library steps.py justification.json
Justification: release
  Version 2.0 is ready to ship

JP020 error: steps.py cannot be imported: ModuleNotFoundError at line 14: No module named 'release_checks'
  fix: Install the module in the environment jpipe-runner runs in, or pass the directory that holds it as a python path.
  Traceback (most recent call last):
    File "steps.py", line 14, in <module>
      from release_checks import RELEASE
  ModuleNotFoundError: No module named 'release_checks'

1 diagnostic (1 error)
verdict: invalid (nothing ran)
$ echo $?
3
$ jpipe-runner --library steps.py --python-path checks justification.json
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

- **A module of your own** is found only through `--python-path`, even one beside the
  library: the library's own directory is not added for you. Pass `-p .` for the working
  directory.
- **A package** (`import pandas`) must be installed in the environment jpipe-runner runs
  in. The Homebrew, pipx and Ubuntu packages run it in an environment of its own, which
  sees none of your packages: install jpipe-runner in your project's environment instead
  ([`cli.md`](cli.md#step-libraries-that-import-packages)). `-v` logs which Python runs
  the steps.

### A step library written for version 3

It stops at its first import, `from jpipe_runner.framework…`, with an `ImportError` that
names what replaced it. So does every library the jPipe compiler generated, up to 2.5.0.
[`migration-v3-v4.md`](migration-v3-v4.md) takes it to version 4.

### Two libraries called `steps.py`

Each library is imported as the module named after its file, so two files with the same
name cannot run together, even from different directories (`JP021`). Name each library
after its model: `tested_steps.py`, `documented_steps.py`
([`authoring.md`](authoring.md#library-file-names-must-differ)).

## Running

### Every evidence fails: its file does not exist

The paths an evidence observes are relative to the directory the command runs in, not to
the step library. Run from the wrong directory, every file is missing:

```console
$ jpipe-runner --library release/steps.py release/justification.json
Justification: release
  Version 2.0 is ready to ship

  ✘ Evidence    The test suite passes         # release:e1
      steps.the_test_suite_passes: mock/junit.xml, observed as 'report', does not exist
      observed mock/junit.xml (unreachable)
  ✘ Evidence    The changelog is up to date   # release:e2
      steps.the_changelog_is_up_to_date: mock/CHANGELOG.md, observed as 'changelog', does not exist
      observed mock/CHANGELOG.md (unreachable)
  - Strategy    All release gates pass        # release:s
      not run: release:e1, release:e2 did not pass
  - Conclusion  Version 2.0 is ready to ship  # release:c
      not run: release:e1, release:e2 did not pass

JP019 error [release:e1]: mock/junit.xml, observed as 'report', does not exist
  fix: Make sure the artifact exists when the runner runs, at this path relative to the directory it runs in, or correct the path in observes={...}.
JP019 error [release:e2]: mock/CHANGELOG.md, observed as 'changelog', does not exist
  fix: Make sure the artifact exists when the runner runs, at this path relative to the directory it runs in, or correct the path in observes={...}.

4 elements (2 failed, 2 skipped)
2 diagnostics (2 errors)
verdict: fail
$ echo $?
1
```

`cd` into the directory the paths start from, here `release/`, and run from there. When
only one evidence fails this way, its file has not been made yet (run the build or the
tests first), or the path in its `observes` is wrong. To check the library before the
files exist, use `--dry-run`, which observes nothing.

### The justification is a `.jd` file

The runner reads the JSON the jPipe compiler writes, not the jPipe source:

```console
$ jpipe-runner --library steps.py release.jd
JP001 error: not JSON: Expecting value (line 1, column 1)
  fix: This is a jPipe source file: compile it with `jpipe process -f JSON`, and pass the JSON file the compiler writes.

1 diagnostic (1 error)
verdict: invalid (nothing ran)
$ echo $?
3
```

Compile it first: `jpipe process -i release.jd -m release -f JSON -o justification.json`.

### A diagram's file name is refused

The suffix of a diagram's file is its format. One that is not a format is a usage error,
and nothing runs:

```console
$ jpipe-runner --library steps.py --diagram release.txt justification.json
usage: jpipe-runner [-h] -l PATH [-p DIR] [--strict] [--dry-run] [--json]
                    [--report PATH] [--diagram PATH] [--dataflow PATH]
                    [--colour {auto,always,never}] [-v | -q] [--version]
                    JUSTIFICATION
jpipe-runner: error: --diagram release.txt: the suffix of the file is its format, one of dot, gif, jpeg, jpg, pdf, png, svg
$ echo $?
2
```

### Something was skipped, and the command exited 0

A justification whose elements passed or were skipped, with none failed, has the verdict
`skip`. A skip is not a failure, so the exit code is 0. To fail a CI step on a skip, run
with `--strict`, which also counts validation's warnings as errors.

### No colours in GitHub Actions

`--colour auto`, the default, colours the text report only on a terminal, and GitHub
Actions is not one, although its log shows colours. Pass `--colour always` there.

## Impact and staleness

### `status` refuses the report of a dry run

`status` compares the files a run observed with the files now, and a dry run observes none:

```console
$ jpipe-runner status report.json
jpipe-runner: error: report.json is the report of a run in which no step ran: it observed no file
$ echo $?
3
```

Write the report with a run that calls the steps: `--report report.json` without
`--dry-run`. The same goes for the report of a run that stopped before any step (`invalid`).

### `impact --since` cannot list the changes

`--since` asks git for the files that differ from a revision, so it needs git, a
repository, and that revision in it. In GitHub Actions, `actions/checkout` fetches only the
last commit by default, so `origin/main` is not there: check out with `fetch-depth: 0`.
When git cannot list the changes, the exit code is 4, and git's own error says why.

## Still stuck

Open an [issue](https://github.com/jpipe-mcscert/jpipe-runner/issues) with the command you
ran, its output with `-vv`, and, if there is one, the JSON report (`--report report.json`).
