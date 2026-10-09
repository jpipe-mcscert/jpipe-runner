"""The command line, ``jpipe-runner`` (ADR-0023).

``jpipe-runner -l steps.py justification.json`` runs a justification: it loads the model
the jPipe compiler wrote, imports the step libraries, validates them against it, runs the
steps, and reports. Every way this ends has a report (ADR-0011), and an exit code that a
CI pipeline can act on (``ExitCode``).

stdout carries the report and nothing else: the text report, or the JSON report with
``--json``. ``--report``, ``--diagram`` and ``--dataflow`` write files. stderr carries the
logs, the errors and argparse's usage. The paths an evidence observes, and those the
report shows, are relative to the working directory.
"""

import argparse
import glob
import logging
import os
import shutil
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

from jpipe_runner import __version__, diagram, engine, impact, json_report, loader, text_report
from jpipe_runner.diagnostics import shown_path
from jpipe_runner.engine import Verdict
from jpipe_runner.libraries import LibraryLoadError, imported
from jpipe_runner.model import InvalidJustificationError, Justification
from jpipe_runner.report import RunReport
from jpipe_runner.steps import StepRegistry, is_glob

_LOG = logging.getLogger(__name__)

_PROGRAM = "jpipe-runner"
_COLOURS = ("auto", "always", "never")


class ExitCode(IntEnum):
    """What ``jpipe-runner`` exits with."""

    OK = 0
    """The justification passed, was skipped (unless ``--strict``), or a dry run found it
    valid."""
    FAILED = 1
    """An element failed, or, with ``--strict``, the justification was skipped."""
    USAGE = 2
    """The command line is wrong: an unknown option, a missing library, an output whose
    format cannot be told from its suffix."""
    INVALID = 3
    """Nothing ran: the model was refused, a step library could not be imported, or
    validation reported an error."""
    IO = 4
    """A file could not be read or written, or Graphviz could not draw a diagram."""


def exit_code(verdict: Verdict, *, strict: bool = False) -> ExitCode:
    """The exit code of a run that ended with ``verdict``. A strict run fails a skip."""
    if verdict is Verdict.FAIL or (verdict is Verdict.SKIP and strict):
        return ExitCode.FAILED
    if verdict is Verdict.INVALID:
        return ExitCode.INVALID
    return ExitCode.OK


def parser() -> argparse.ArgumentParser:
    """The parser of the command that runs a justification."""
    parser = argparse.ArgumentParser(
        prog=_PROGRAM,
        description="Run a jPipe justification against the Python step libraries that "
        "implement its evidence and its reasoning, and report its verdict.",
        epilog="Exit codes: 0 the justification holds (or was skipped, or a dry run found it "
        "valid); 1 it failed; 2 usage error; 3 nothing ran (refused model, library that "
        "cannot be imported, validation error); 4 a file could not be read or written.",
    )
    _add_inputs(parser)
    run = parser.add_argument_group("running")
    run.add_argument(
        "--strict",
        action="store_true",
        help="count validation warnings as errors, and fail a skipped justification",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the step libraries against the justification, and call no step",
    )
    outputs = parser.add_argument_group("outputs")
    outputs.add_argument(
        "--json",
        action="store_true",
        help="print the JSON report on stdout, instead of the text report",
    )
    outputs.add_argument(
        "--report", type=Path, metavar="PATH", help="write the JSON report to PATH"
    )
    formats = ", ".join(diagram.FORMATS)
    outputs.add_argument(
        "--diagram",
        type=Path,
        metavar="PATH",
        help=f"draw the justification, with the run over it, to PATH; its suffix is the "
        f"format: {formats}",
    )
    outputs.add_argument(
        "--dataflow",
        type=Path,
        metavar="PATH",
        help="draw the justification with the files and variables its steps declare to PATH",
    )
    outputs.add_argument(
        "--colour",
        choices=_COLOURS,
        default="auto",
        help="colour the text report: on a terminal unless NO_COLOR is set (auto, the "
        "default), always, or never",
    )
    _add_logging(parser)
    parser.add_argument("--version", action="version", version=f"{_PROGRAM} {__version__}")
    return parser


def impact_parser() -> argparse.ArgumentParser:
    """The parser of ``jpipe-runner impact``."""
    parser = argparse.ArgumentParser(
        prog=f"{_PROGRAM} impact",
        description="List the evidence that observes changed files, and every element "
        "above it, from what the step libraries declare. No step is called.",
    )
    _add_inputs(parser)
    changes = parser.add_mutually_exclusive_group(required=True)
    changes.add_argument(
        "--changed",
        action="append",
        metavar="PATH",
        help="a changed file, relative to the working directory; repeat for several",
    )
    changes.add_argument(
        "--since",
        metavar="REF",
        help="the files that differ from the git revision REF, and those git does not track",
    )
    _add_logging(parser)
    parser.set_defaults(strict=False, dry_run=True)
    return parser


def status_parser() -> argparse.ArgumentParser:
    """The parser of ``jpipe-runner status``."""
    parser = argparse.ArgumentParser(
        prog=f"{_PROGRAM} status",
        description="Compare the files a run observed, as its JSON report recorded them, "
        "with the files now, and list what is stale. No step is called.",
        epilog="Exit codes: 0 nothing changed; 1 something is stale; 3 the file is not a "
        "report of a run that observed files; 4 it cannot be read.",
    )
    parser.add_argument(
        "report",
        metavar="REPORT",
        type=Path,
        help="the JSON report of a run (--report), read from the directory the run ran in",
    )
    _add_logging(parser)
    return parser


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    """The justification, its step libraries and their python path."""
    parser.add_argument(
        "justification",
        metavar="JUSTIFICATION",
        type=Path,
        help="the justification, as the JSON file the jPipe compiler writes "
        "(jpipe process -f JSON)",
    )
    parser.add_argument(
        "-l",
        "--library",
        action="append",
        required=True,
        metavar="PATH",
        help="a step library: a Python file, or a glob of files (quoted); repeat for several",
    )
    parser.add_argument(
        "-p",
        "--python-path",
        action="append",
        default=[],
        type=Path,
        metavar="DIR",
        help="a directory the step libraries import modules from; repeat for several",
    )


def _add_logging(parser: argparse.ArgumentParser) -> None:
    logs = parser.add_mutually_exclusive_group()
    logs.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="log what the runner does, on stderr: -v for each step, -vv for details",
    )
    logs.add_argument("-q", "--quiet", action="store_true", help="log only errors")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line on ``argv``, by default the process's arguments, and return
    the exit code. A first argument ``impact`` or ``status`` names a subcommand."""
    arguments = sys.argv[1:] if argv is None else list(argv)
    command = _RUN
    if arguments and arguments[0] in _SUBCOMMANDS:
        command = _SUBCOMMANDS[arguments.pop(0)]
    reader = command.parser()
    try:
        options = reader.parse_args(arguments)
        command.check(reader, options)
    except SystemExit as stop:  # argparse exits on --help, --version and usage errors
        return stop.code if isinstance(stop.code, int) else ExitCode.USAGE
    with _logging(options.verbose, options.quiet):
        try:
            return command.run(options)
        except OSError as error:
            _LOG.error("%s", _reason(error))
            return ExitCode.IO


def _check_outputs(command: argparse.ArgumentParser, options: argparse.Namespace) -> None:
    """Refuse, before anything runs, the outputs that could not be written."""
    outputs = {
        "--report": options.report,
        "--diagram": options.diagram,
        "--dataflow": options.dataflow,
    }
    seen: dict[Path, str] = {}
    for flag, path in outputs.items():
        if path is None:
            continue
        if path.is_dir():
            command.error(f"{flag} {path}: a directory, where a file is expected")
        suffix = path.suffix.removeprefix(".").lower()
        if flag != "--report" and suffix not in diagram.FORMATS:
            formats = ", ".join(diagram.FORMATS)
            command.error(f"{flag} {path}: the suffix of the file is its format, one of {formats}")
        if (same := seen.get(path.resolve())) is not None:
            command.error(f"{same} and {flag} both write {path}")
        seen[path.resolve()] = flag


def _run(options: argparse.Namespace) -> int:
    _check_graphviz(options.diagram, options.dataflow)
    # The working directory, as a relative path: a step receives the files it observes
    # relative to it, as its author wrote them, and a reason that names one reads the same
    # on every machine.
    root = Path()
    _LOG.info("steps run with Python %s, in %s", sys.executable, Path.cwd())
    justification, report = _report(options, root)
    _LOG.info("verdict: %s", report.verdict)
    code = exit_code(report.verdict, strict=options.strict)
    report, drawn = _draw(options, justification, report, root)
    saved = _save(options.report, report)
    if options.json:
        sys.stdout.write(json_report.dumps(report))
    else:
        colour = _colour(options.colour)
        unicode = text_report.use_unicode(sys.stdout)
        sys.stdout.write(text_report.render(report, colour=colour, unicode=unicode))
    return code if drawn and saved else ExitCode.IO


def _check_graphviz(*paths: Path | None) -> None:
    """Raise ``FileNotFoundError`` if a diagram needs Graphviz's ``dot``, and it is not
    installed: nothing should run for an output that cannot be drawn."""
    needed = [path for path in paths if path is not None and path.suffix.lower() != ".dot"]
    if needed and shutil.which("dot") is None:
        raise FileNotFoundError(
            f"Graphviz's dot is needed to draw {needed[0]}, and is not installed or not on "
            "the PATH: install Graphviz (https://graphviz.org/download/), or draw a .dot file"
        )


def _report(options: argparse.Namespace, root: Path) -> tuple[Justification | None, RunReport]:
    """The model, unless it was refused, and the report of the run, however it ended."""
    libraries = _libraries(options.library)
    try:
        justification = loader.load(options.justification)
    except InvalidJustificationError as error:
        return None, RunReport.refused(error, strict=options.strict)
    _LOG.info(
        "loaded %s from %s: %d elements",
        justification.name,
        options.justification,
        len(justification),
    )
    try:
        with imported(libraries, options.python_path) as modules:
            _LOG.debug("sys.path: %s", sys.path)
            registry = StepRegistry.from_modules(modules)
            _LOG.info("step libraries imported: %d (%d steps)", len(modules), len(registry))
            result = engine.run(
                justification,
                registry,
                strict=options.strict,
                root=root,
                dry_run=options.dry_run,
            )
    except LibraryLoadError as error:
        report = RunReport.not_imported(justification, error, strict=options.strict, root=root)
        return justification, report
    return justification, RunReport.of(result, root)


def _libraries(patterns: Sequence[str]) -> list[Path]:
    """The step library files: each path as it is, each glob expanded and sorted. Raises
    ``FileNotFoundError`` for a glob that matches nothing."""
    files: list[Path] = []
    for pattern in patterns:
        if not is_glob(pattern):
            files.append(Path(pattern))
            continue
        matched = sorted(glob.glob(pattern, recursive=True))
        if not matched:
            raise FileNotFoundError(f"no step library matches {pattern!r}")
        files.extend(Path(path) for path in matched)
    _LOG.debug("step libraries: %s", [str(file) for file in files])
    return files


def _draw(
    options: argparse.Namespace,
    justification: Justification | None,
    report: RunReport,
    root: Path,
) -> tuple[RunReport, bool]:
    """The report, recording the diagrams drawn, and whether every one asked for was."""
    drawings: list[tuple[Path | None, diagram.View, Callable[[RunReport, str], RunReport]]] = [
        (options.diagram, diagram.View.JUSTIFICATION, RunReport.with_diagram),
        (options.dataflow, diagram.View.DATAFLOW, RunReport.with_dataflow),
    ]
    drawn = True
    for path, view, record in drawings:
        if path is None:
            continue
        if justification is None:
            _LOG.warning("the model was refused, so %s is not drawn", path)
            continue
        try:
            diagram.write(path, justification, report, view=view)
        except OSError as error:
            _LOG.error("%s", _reason(error))
            drawn = False
            continue
        _LOG.info("drew the %s view at %s", view, path)
        report = record(report, shown_path(str(path), root))
    return report, drawn


def _save(path: Path | None, report: RunReport) -> bool:
    """Write the JSON report to ``path``, if one is given; whether it was written."""
    if path is None:
        return True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_report.dumps(report), encoding="utf-8")
    except OSError as error:
        _LOG.error("cannot write the report to %s: %s", path, _reason(error))
        return False
    _LOG.info("wrote the JSON report to %s", path)
    return True


def _check_since(reader: argparse.ArgumentParser, options: argparse.Namespace) -> None:
    if options.since is not None and options.since.startswith("-"):
        reader.error(f"--since {options.since}: not a git revision")


def _check_nothing(reader: argparse.ArgumentParser, options: argparse.Namespace) -> None:
    """No check beyond the parser's."""


def _impact(options: argparse.Namespace) -> int:
    """What changed files reach in the argument, from the declarations of a dry run."""
    # Asked first: importing the libraries writes files of its own, such as __pycache__.
    if options.since is not None:
        changed = impact.changed_since(options.since)
    else:
        changed = _relative(options.changed)
    _, report = _report(options, Path())
    if not any(element.step for element in report.elements):
        # A refused model, libraries that cannot be imported or that bind nothing: there is
        # nothing declared to analyze, and the report says why.
        unicode = text_report.use_unicode(sys.stdout)
        sys.stdout.write(text_report.render(report, unicode=unicode))
        return ExitCode.INVALID
    document = json_report.document(report)
    sys.stdout.write(impact.render_impact(document, impact.affected(document, changed)))
    return ExitCode.OK


def _relative(paths: Sequence[str]) -> list[str]:
    """``paths``, relative to the working directory; those outside it are left out."""
    here = Path.cwd().resolve()
    inside: list[str] = []
    for path in paths:
        try:
            inside.append(Path(path).resolve().relative_to(here).as_posix())
        except ValueError:
            _LOG.warning("%s is outside the working directory, and is left out", path)
    return inside


def _status(options: argparse.Namespace) -> int:
    """Whether the files a run observed have changed since its report was written."""
    try:
        document = impact.read(options.report)
    except impact.InvalidReportError as error:
        _LOG.error("%s", error)
        return ExitCode.INVALID
    if document["verdict"] in (Verdict.INVALID, Verdict.VALID):
        _LOG.error(
            "%s is the report of a run in which no step ran: it observed no file", options.report
        )
        return ExitCode.INVALID
    changes = impact.stale(document)
    reached = [a for e in document["elements"] for a in e["artifacts"] if a["reachable"]]
    vanished = [change for change in changes if change.kind is impact.ChangeKind.VANISHED]
    if reached and len(vanished) == len(reached):
        _LOG.warning(
            "every file the run observed is missing: run status from the directory the run "
            "ran in, where the report's paths start"
        )
    sys.stdout.write(impact.render_stale(document, changes))
    return ExitCode.FAILED if changes else ExitCode.OK


def _colour(choice: str) -> bool:
    """Whether to colour the text report: ``always`` and ``never`` override ``NO_COLOR``."""
    if choice == "auto":
        return text_report.use_colour(sys.stdout, os.environ)
    return choice == "always"


def _reason(error: OSError) -> str:
    """What went wrong, in one line: the message, with the file it is about."""
    if error.filename is not None and error.strerror:
        return f"{error.filename}: {error.strerror}"
    return str(error)


class _Format(logging.Formatter):
    """``jpipe-runner: <level>: <message>``, with the logger's name when ``named``."""

    def __init__(self, named: bool) -> None:
        super().__init__()
        self._named = named

    def format(self, record: logging.LogRecord) -> str:
        where = f"{record.name}: " if self._named else ""
        return f"{_PROGRAM}: {record.levelname.lower()}: {where}{record.getMessage()}"


@contextmanager
def _logging(verbosity: int, quiet: bool) -> Iterator[None]:
    """Log the package's records on stderr, at the level the options ask for, while the
    command runs. The logger is left as it was found."""
    logger = logging.getLogger("jpipe_runner")
    if quiet:
        level = logging.ERROR
    else:
        level = {0: logging.WARNING, 1: logging.INFO}.get(verbosity, logging.DEBUG)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Format(named=verbosity > 1))
    saved_level, saved_propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(saved_level)
        logger.propagate = saved_propagate


@dataclass(frozen=True)
class _Command:
    """A command of the command line: its parser, what it checks before anything runs,
    and what it does."""

    parser: Callable[[], argparse.ArgumentParser]
    check: Callable[[argparse.ArgumentParser, argparse.Namespace], None]
    run: Callable[[argparse.Namespace], int]


_RUN = _Command(parser, _check_outputs, _run)
_SUBCOMMANDS = {
    "impact": _Command(impact_parser, _check_since, _impact),
    "status": _Command(status_parser, _check_nothing, _status),
}
