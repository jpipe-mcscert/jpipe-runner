---
status: accepted
date: 2026-10-09
decision-makers: Sébastien Mosser
---

# ADR-0023: The command line: one command, its subcommands, its outputs and its exit codes

## Context and Problem Statement

v3's command line hid most of what went wrong (#124):

- **Every error exited 1.** `WorkflowError.exit_code` defaulted to 1 and nothing passed
  anything else, so a CI script could not tell a usage error from a validation error or a
  justification that does not hold.
- **Logging did not work.** The only handler was an in-memory buffer at `WARNING`, so
  `--verbose` changed nothing that could be seen.
- **Options did not do what they said.** `--diagram PATTERN` was parsed and never read.
  `--output-path` named a directory, so `--output diagram.png`, which the README taught,
  abbreviated to it and created a directory called `diagram.png`. `-v` was `--variable`.
- **The working directory was always importable**: `--python-path` defaulted to `.`.

#124 sketched v4's command line before M5 was built. M5 then drew a justification in two
views (ADR-0022), and made the JSON report the contract (ADR-0011), which #146 (`status`)
and the GitHub Action (MB1) will read. A sketch with `-o PATH` and `-f FORMAT` for one
diagram, and `--report {text,json}` beside them, no longer fitted: two views need two
paths, and options that take a format sat beside options that take a path.

What should the command line be, where should its outputs go, and how should it end?

## Decision Drivers

- **A CI script acts on the exit code alone**: a failed justification, a broken library
  and a broken environment are different problems, with different owners.
- **A program reads the JSON report, never the text** (ADR-0011), and a person reads the
  text: one run should serve both.
- **Every option does what its name says**, and an option whose output cannot be produced
  is refused before any step runs.
- **One way to start the runner**: `jpipe-runner` and `python -m jpipe_runner` import the
  same modules (ADR-0020).
- **Room for `impact` and `status` (#146)** without breaking the command that runs a
  justification.

## Considered Options

For the shape of the command:

1. Running a justification is the command; `impact` and `status` are subcommands,
   recognized by their first word.
2. Explicit subcommands for everything: `jpipe-runner run …`.
3. One command, whose flags switch it to impact analysis or staleness.

For the outputs:

1. Each file is an option named after what it holds, taking its path: `--report`,
   `--diagram`, `--dataflow`; `--json` prints the JSON report on stdout.
2. #124's sketch: `--report {text,json}` for stdout, `-o PATH` for the diagram, `-f FMT`
   for its format.
3. One directory for everything, with default names.

For a file that cannot be read or written:

1. Exit 4, with the error on stderr, and no diagnostic code.
2. A diagnostic code in the report.

## Decision Outcome

Chosen options: **running is the command, with subcommands for the rest**, **each file
named by its own option**, and **exit 4 for I/O, without a code**, because they keep the
common invocation short, make every output explicit, and keep the report about the
argument.

```
jpipe-runner -l/--library PATH|GLOB [-l …]... [-p/--python-path DIR]...
             [--json] [--report PATH] [--diagram PATH] [--dataflow PATH]
             [--strict] [--dry-run] [--colour {auto,always,never}]
             [-v | -vv | -q] [--version]  JUSTIFICATION
```

**Inputs.**

- `JUSTIFICATION` is the JSON file the jPipe compiler writes. Its name is not checked: the
  loader checks its content (`JP001`). A `.jd` file, the source the compiler reads, is
  refused with a fix that says to compile it.
- `-l/--library` is required: without a library, every evidence is unbound (`JP005`), and
  nothing can run. It names a file, which the documentation, ADR-0020 and `JP020`/`JP021`
  call a step library, so it is not `--steps`. A glob is expanded, sorted, with `**`
  recursive; one that matches nothing is an I/O error, as a missing file is.
- `-p/--python-path` has no default. Only the directories it names are added to
  `sys.path` (ADR-0020); a v3 user whose library imports a module next to it passes
  `-p .`. `python -m jpipe_runner` drops the working directory that Python puts first on
  `sys.path`, so that it imports what the `jpipe-runner` script imports. Python imports
  the package before its `__main__`, so the package's top level loads only the standard
  library, and the public API is loaded when it is first used.
- The root of the run, against which evidence observes its files and the report shows its
  paths, is the working directory. There is no `--root`: `cd` does it.

**Outputs.** stdout carries the report and nothing else: the text report, or the JSON
report with `--json`. stderr carries the logs, the errors and argparse's usage.

- `--report PATH` writes the JSON report to a file, whatever stdout shows, so that one run
  gives a person the text and a program the JSON.
- `--diagram PATH` draws the justification with the run over it, and `--dataflow PATH` its
  dataflow view (ADR-0022). The suffix is the format; there is no format option.
- Before anything runs, the command refuses (exit 2) an output whose suffix is not a
  format, a path that is a directory, and two outputs that name one file. A v3 habit such
  as `--diagram '*'` is refused there rather than misread. When a diagram needs Graphviz's
  `dot` and it is not installed, nothing runs (exit 4): no step should run for an output
  that cannot be produced.
- The run, then the diagrams, then the JSON file, then stdout: the report records where
  each diagram was written (ADR-0024). An output that fails after the run leaves the
  report written without it, and the command exits 4.
- `--colour auto` colours the text report on a terminal, unless `NO_COLOR` is set;
  `always` and `never` override `NO_COLOR`, as https://no-color.org asks. GitHub Actions
  is not a terminal, and shows colours: use `--colour always` there. It is spelled the
  Canadian way, as the project's identifiers are.

**Exit codes**, `cli.ExitCode`:

| Code | When |
|---|---|
| 0 | the verdict is `pass`, `valid` (a dry run), or `skip` unless `--strict` |
| 1 | the verdict is `fail`, or `skip` with `--strict` |
| 2 | the command line is wrong |
| 3 | nothing ran: the model was refused, a library could not be imported, or validation reported an error |
| 4 | a file could not be read or written, or a diagram could not be drawn |

4 takes precedence over the verdict: an output asked for is missing, and the report, if
it was written, still holds the verdict. `--strict` counts validation's warnings as errors
(ADR-0010) and fails a skipped justification (ADR-0021).

**An I/O error is not a diagnostic.** A justification, a library or a python path that
cannot be read means the runner was invoked wrongly, as ADR-0020 decided for a library:
there is no model to report on, so there is no report, only the error on stderr. No code
is added: a code describes the argument or its steps, and the report stays about them.

**Logging.** `main` gives the `jpipe_runner` logger one handler on stderr for as long as
it runs, and leaves it as it found it, so that importing the package configures nothing.
The default shows warnings and errors; `-v` shows what the run does (the model loaded, the
libraries imported, each element's status, the interpreter that runs the steps); `-vv`
adds details, such as each step called and `sys.path`, with the logger's name; `-q` shows
errors only. Records read `jpipe-runner: <level>: <message>`. `-v` was `--variable` in
v3; a v3 command that uses it is a usage error, not a silent change.

**Subcommands.** A first argument `impact` or `status` names a subcommand (#146); any
other runs a justification. A justification file named `status` is written `./status`.

`diagram.default_name`, which ADR-0022 provided for the command line to name a diagram,
is gone: the command line takes each diagram's path.

### Consequences

- Good, because a CI script can tell a failed justification (1), a broken library or
  model (3) and a broken environment (4) apart.
- Good, because one run gives the text to a person and the JSON to a program.
- Good, because every output is named by the option that writes it, and refused before a
  step runs if it cannot be produced.
- Bad, because v3 commands do not run unchanged: `-v`, `-o`, `-f`, `--output-path` and
  the default python path are gone, and the Action must be rewritten (MB1).
- Bad, because `impact` and `status` cannot be the names of a justification file without
  `./`.

### Confirmation

- `tests/unit/test_cli.py` runs the command in process: every exit code, every output,
  the usage errors, the logs and the colours, and every scenario's command.
- `tests/e2e/test_scenarios.py` runs `python -m jpipe_runner --json` on every scenario in
  a subprocess, and compares its whole report with the scenario's golden file.
- `tests/e2e/test_cli.py` checks that the script and `python -m` give the same report, and
  that a module of the working directory reaches neither a step library nor the runner's
  own dependencies, however the runner is started.
- `tests/unit/test_cli_doc.py` checks that `docs/cli.md` documents every option and every
  exit code.

## Pros and Cons of the Options

### Running is the command, with subcommands

- Good, because the command people type most is the shortest, and the one #124 sketched.
- Bad, because two words cannot name a justification file.

### Explicit subcommands

- Good, because nothing is ambiguous.
- Bad, because every invocation gains `run`.

### Flags that switch the command

- Good, because there is one parser.
- Bad, because some flags turn others off, which `--help` cannot explain.

### Each file named by its own option

- Good, because the option says what the file holds, and every view can be drawn in one
  run.
- Bad, because the format of a diagram cannot differ from its suffix.

### `--report {text,json}`, `-o`, `-f`

- Good, because it is what #124 sketched.
- Bad, because it draws one view per run, and `--report` takes a format where its
  neighbours take a path.

### One output directory

- Good, because one option covers everything.
- Bad, because names are imposed, and the JSON report cannot go to stdout.

### A diagnostic code for I/O

- Good, because the report would say why a diagram is missing.
- Bad, because there is no report when an input cannot be read, and a code would describe
  the environment rather than the argument.

## More Information

- #124 (this decision), #146 (`impact`, `status`), #132 (the Action).
- [ADR-0011](0011-json-report-is-the-machine-readable-contract.md), the report;
  [ADR-0020](0020-importing-step-libraries.md), importing libraries;
  [ADR-0021](0021-execution-semantics.md), verdicts;
  [ADR-0022](0022-diagrams-follow-the-compiler.md), diagrams;
  [ADR-0024](0024-dry-run-verdict-and-both-diagrams.md), the dry run.
