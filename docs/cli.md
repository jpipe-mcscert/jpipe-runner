# The command line

`jpipe-runner` runs a justification: it reads the model the jPipe compiler wrote, imports
the Python step libraries that implement its evidence and its reasoning, checks that they
fit the model, calls them, and reports the verdict. This page describes every option and
every exit code. [`tutorial.md`](tutorial.md) walks through a first run,
[`end-to-end.md`](end-to-end.md) follows one example from the argument to its verdict, and
[`authoring.md`](authoring.md) explains how to write a step library.

```
jpipe-runner -l/--library PATH|GLOB [-l …]... [-p/--python-path DIR]...
             [--json] [--report PATH] [--diagram PATH] [--dataflow PATH]
             [--strict] [--dry-run] [--colour {auto,always,never}]
             [-v | -vv | -q] [--version]  JUSTIFICATION
jpipe-runner impact -l … [-p …]... (--changed PATH [--changed …]... | --since REF) JUSTIFICATION
jpipe-runner status REPORT
```

`python -m jpipe_runner` is the same command. `impact` and `status` are subcommands, and
come first: [impact analysis](#impact-analysis) lists what changed files reach in the
argument, and [staleness](#staleness) what has changed since a run, without running any
step. A justification file named `impact` or `status` is written `./status`.

## A run

Run it in the directory the evidence observes its files from: the paths a step library
declares, and those the report shows, are relative to it. Here, the
[release example](end-to-end.md):

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

## Options

| Option | |
|---|---|
| `JUSTIFICATION` | The justification: the JSON file the jPipe compiler writes (`jpipe process -f JSON`). A `.jd` file is its source, and is refused with a fix that says to compile it. |
| `-l PATH`, `--library PATH` | A step library: a Python file, or a glob of files, quoted so that the shell leaves it alone (`--library 'checks/*.py'`, with `**` for any depth). Required; repeat it for several. A library is imported as the module named after its file. |
| `-p DIR`, `--python-path DIR` | A directory the step libraries import modules from, such as the one that holds a helper module; repeat it for several. Nothing else is importable: pass `-p .` to import modules from the working directory. |
| `--strict` | Count validation's warnings as errors, and fail a skipped justification (exit 1). |
| `--dry-run` | Validate the step libraries against the justification, and call no step: the verdict is `valid`, or `invalid`. |
| `--json` | Print the JSON report on stdout, instead of the text report. |
| `--report PATH` | Write the JSON report to `PATH`, whatever stdout shows. |
| `--diagram PATH` | Draw the justification, with the run over it, to `PATH`. |
| `--dataflow PATH` | Draw the justification with the files and variables its steps declare to `PATH`. |
| `--colour WHEN` | Colour the text report: `auto` (the default) on a terminal unless `NO_COLOR` is set, `always`, or `never`. |
| `-v`, `--verbose` | Log what the run does, on stderr; `-vv` logs details. |
| `-q`, `--quiet` | Log errors only. |
| `--version` | Print the version. |
| `-h`, `--help` | Print the options. |

## Outputs

**stdout carries the report, and nothing else.** By default it is the text report, for
the person at the terminal: one line per element, in the order run, then the diagnostics,
the summary and the verdict. Its layout may change in any release. With `--json`, it is
the JSON report instead, the contract for programs, described in
[`report-schema.md`](report-schema.md). `--report PATH` writes the JSON report to a file
as well, so that one run gives the text to a person and the JSON to a program.

**Diagrams** are drawn as the jPipe compiler draws them, with the run's statuses over them
([ADR-0022](adr/0022-diagrams-follow-the-compiler.md)). `--diagram` draws the argument,
`--dataflow` adds the files each evidence observes and the variables the steps produce
and consume; both can be drawn in one run. The suffix of the file is its format: `dot`,
`gif`, `jpeg`, `jpg`, `pdf`, `png` or `svg`. Every format but `dot` needs Graphviz's `dot`
command. The report records where each diagram was written, and the text report says so
above the verdict.

**Outputs are checked before anything runs.** An output whose suffix is not a format, that
is a directory, or that two options would both write, is a usage error, and so nothing
runs:

```console
$ jpipe-runner --library steps.py --diagram release.png --dataflow release.png justification.json
usage: jpipe-runner [-h] -l PATH [-p DIR] [--strict] [--dry-run] [--json]
                    [--report PATH] [--diagram PATH] [--dataflow PATH]
                    [--colour {auto,always,never}] [-v | -q] [--version]
                    JUSTIFICATION
jpipe-runner: error: --diagram and --dataflow both write release.png
$ echo $?
2
```

A diagram that needs Graphviz when it is not installed stops the command before any step
runs, with exit code 4: draw a `.dot` file instead, or install Graphviz.

**stderr carries everything else**: the logs, the errors, and the usage when the command
line is wrong.

**Colour.** `--colour auto` colours the text report only on a terminal, and never when
the `NO_COLOR` environment variable is set. GitHub Actions shows colours, but is not a
terminal: use `--colour always` there. `always` and `never` override `NO_COLOR`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The justification holds: its verdict is `pass`. Also `skip`, unless `--strict`, and `valid`, for a dry run. |
| 1 | The justification does not hold: an element failed (`fail`), or, with `--strict`, one was skipped. |
| 2 | The command line is wrong: an unknown option, no `--library`, an output that cannot be written. Nothing ran. |
| 3 | Nothing could run (`invalid`): the justification was refused, a step library could not be imported, or validation reported an error. The report says why. |
| 4 | A file could not be read or written: the justification, a step library, a python path, the JSON report or a diagram. |

When a file the command was asked to write cannot be written after the run, the report is
still printed, and the exit code is 4: the verdict is in the report.

A file that cannot be read is reported on stderr, and there is no report, since nothing
ran:

```console
$ jpipe-runner --library steps.py release.json
jpipe-runner: error: release.json: No such file or directory
$ echo $?
4
```

## A dry run

`--dry-run` imports the step libraries and validates them against the justification, but
calls no step, and observes no file. It is how to check a library before the artifacts its
evidence observes exist:

```console
$ jpipe-runner --library steps.py --dry-run justification.json
Justification: release
  Version 2.0 is ready to ship

verdict: valid (a dry run: no step was called)
$ echo $?
0
```

Its JSON report lists every element, with its step and what that step declares, and a
null status. `--dry-run --dataflow flow.svg` draws the dataflow the library declares
without running it. A library that does not validate gives `invalid`, and exit code 3, as
any run would.

## Logging

The logs go to stderr, so that they never mix with the report.

- By default, only warnings and errors: a diagram that is not drawn, a file that cannot be
  read or written.
- `-v` also logs what the run does: the justification loaded, the step libraries imported,
  the Python that runs the steps, each element's status, and each file written.
- `-vv` adds details, each with the name of the module that logged it: the step libraries
  a glob matched, `sys.path` while the steps run, each step called.
- `-q` logs errors only.

## Step libraries that import packages

A step library is imported by the Python that runs `jpipe-runner`, so what it imports must
be installed there:

- **A package** (`import pandas`) comes from the environment `jpipe-runner` is installed
  in. Install `jpipe-runner` in your project's own environment, beside the packages your
  steps use: `pip install jpipe-runner` in its virtualenv, or
  `poetry add --group dev jpipe-runner`, then run `jpipe-runner` (or
  `python -m jpipe_runner`) from that environment. The Homebrew, pipx and Ubuntu packages
  install `jpipe-runner` in an environment of its own, which sees none of your packages:
  they suit step libraries that only use Python's standard library.
- **A module of your own**, beside the step library or in a `src/` directory, is found
  only through `--python-path`. The step library's own directory is not added for you.
- A step that imports a module when it runs finds it the same way.

A module that cannot be found stops the run before validation, with `JP020`, the line of
the library that imports it, and exit code 3. `-v` says which Python ran the steps.

## Impact analysis

`jpipe-runner impact` lists the evidence whose declared artifacts match changed files, and
every element above it: what a change puts in question. It reads what the step libraries
declare, as a [dry run](#a-dry-run) does, and runs no step, so it is cheap enough for every
pull request:

```console
$ jpipe-runner impact --library steps.py --changed mock/junit.xml --changed README.md justification.json
Justification: release

Changed files, and the evidence that observes them:
  README.md       (no evidence)
  mock/junit.xml  release:e1

Affected (3 elements):
  Evidence    The test suite passes         # release:e1
  Strategy    All release gates pass        # release:s
  Conclusion  Version 2.0 is ready to ship  # release:c
$ echo $?
0
```

| Option | |
|---|---|
| `JUSTIFICATION` | The justification, as for a run. |
| `-l PATH`, `--library PATH` | A step library, as for a run. |
| `-p DIR`, `--python-path DIR` | A directory the step libraries import modules from, as for a run. |
| `--changed PATH` | A changed file, relative to the working directory (or absolute, under it); repeat it for several. |
| `--since REF` | The files that differ from the git revision `REF` (`origin/main`, a tag, a commit), and those git does not track yet but does not ignore. Needs git. |
| `-v`, `--verbose` | Log what the command does. |
| `-q`, `--quiet` | Log errors only. |
| `-h`, `--help` | Print the options. |

One of `--changed` and `--since` is required. A file matches what an evidence declares as
`Path.glob` matches it: a glob such as `docs/**/*.md` matches every Markdown file under
`docs/`. A changed file no evidence observes is listed, with "(no evidence)": a change
the argument does not cover. The exit code is 0 whatever the change reaches, 3 when the
step libraries declare nothing to analyze (a refused justification, a library that cannot
be imported), and 4 when git cannot list the changes.

## Staleness

`jpipe-runner status` reads the JSON report of a run (`--report`), and compares the files
the run observed with the files as they are now: what it lists no longer holds as the
report says. Run it from the directory the run ran in, where the report's paths start. If
the changelog changed since a run of the release example:

```console
$ jpipe-runner status report.json
Justification: release

Changed since the run:
  changed  mock/CHANGELOG.md  release:e2

Stale (3 elements):
  Evidence    The changelog is up to date   # release:e2
  Strategy    All release gates pass        # release:s
  Conclusion  Version 2.0 is ready to ship  # release:c
$ echo $?
1
```

| Option | |
|---|---|
| `REPORT` | The JSON report of a run. |
| `-v`, `--verbose` | Log what the command does. |
| `-q`, `--quiet` | Log errors only. |
| `-h`, `--help` | Print the options. |

A file is `changed` when its SHA-256 differs from the one recorded, `vanished` when the
run read it and it is gone, `appeared` when the run could not read it and it is there now,
and `added` when a glob an evidence observes matches it and the run did not see it. The
exit code is 0 when nothing changed, 1 when something is stale, 3 when the file is not a
report, or is the report of a run in which no step ran (`invalid`, or a dry run), and 4
when it cannot be read. Nothing runs: to judge the stale elements again, run the
justification.

**Both are only as good as the declarations.** They see the files each evidence declares
it observes, and nothing else: a file a step reads without declaring it is invisible to
them. An evidence that observes nothing is an error (`JP018`), so every evidence declares
something, but whether it declares everything it reads is up to its author.

## Where to go next

- [`report-schema.md`](report-schema.md): every field of the JSON report.
- [`rules.md`](rules.md): every diagnostic code, and how to fix what it reports.
- [ADR-0023](adr/0023-the-command-line.md): why the command line is as it is.
