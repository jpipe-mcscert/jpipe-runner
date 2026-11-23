"""The command line, ``jpipe-runner`` (ADR-0023).

``jpipe-runner -l steps.py justification.json`` runs a justification: it loads the model
the jPipe compiler wrote, imports the step libraries, validates them against it, runs the
steps, and reports. Every way this ends has a report (ADR-0011), and an exit code that a
CI pipeline can act on (``ExitCode``).

stdout carries the report and nothing else: the text report, or the JSON report with
``--json``. ``--report`` and ``--diagram`` write files, and ``--events`` a file the run's
events are written to as it goes (ADR-0030). stderr carries the
logs, the errors and argparse's usage. The paths an evidence observes, and those the
report shows, are relative to the working directory.
"""

import argparse
import glob
import logging
import os
import re
import shutil
import sys
import tempfile
import textwrap
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager, redirect_stdout, suppress
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, NoReturn

from jpipe_runner import __version__, diagram, engine, impact, json_report, loader, text_report
from jpipe_runner.binding import BindingTable
from jpipe_runner.diagnostics import shown_path
from jpipe_runner.engine import RunResult, Verdict
from jpipe_runner.events import RUN_STARTED, EventStream, Preview
from jpipe_runner.libraries import LibraryLoadError, imported
from jpipe_runner.model import InvalidJustificationError, Justification
from jpipe_runner.observables import (
    designates,
    identity,
    is_glob,
)
from jpipe_runner.report import ElementReport, RunReport
from jpipe_runner.steps import StepRegistry

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


class _Stop(Exception):
    """argparse is done before the command runs: it printed the help, the version, or a
    usage error, and ``status`` is the exit code it asks for."""

    def __init__(self, status: int) -> None:
        super().__init__(status)
        self.status = status


class _HelpFormatter(argparse.HelpFormatter):
    """argparse's formatter, except that a text of several lines keeps its lines: the
    exit codes are a list, one code per line (``_exit_codes``). A code whose meaning is
    too long for the terminal wraps under the start of its meaning."""

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        if "\n" not in text:
            return super()._fill_text(text, width, indent)
        return "\n".join(_hanging(line, width, indent) for line in text.splitlines())


_EXIT_CODE_LINE = re.compile(r"^(?P<code>\s+\d+\s+)(?P<meaning>.+)$")


def _hanging(line: str, width: int, indent: str) -> str:
    """``line`` wrapped to ``width`` if it is an exit code, under the start of its
    meaning; any other line as it is."""
    found = _EXIT_CODE_LINE.match(line)
    if found is None:
        return indent + line
    prefix = indent + found["code"]
    return textwrap.fill(
        found["meaning"],
        width,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_on_hyphens=False,
    )


def _exit_codes(*codes: tuple[ExitCode, str]) -> str:
    """The epilog of a command's help: each exit code it can end with, and what it means."""
    return "exit codes:\n" + "\n".join(f"  {code.value}  {meaning}" for code, meaning in codes)


class _Parser(argparse.ArgumentParser):
    """A parser that raises ``_Stop`` where argparse would end the process, so that
    ``main`` returns the exit code instead of exiting. Its help lists the exit codes one
    per line (``_HelpFormatter``)."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(formatter_class=_HelpFormatter, **kwargs)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            self._print_message(message, sys.stderr)
        raise _Stop(status)


def parser() -> argparse.ArgumentParser:
    """The parser of the command that runs a justification."""
    parser = _Parser(
        prog=_PROGRAM,
        description="Run a jPipe justification against the Python step libraries that "
        "implement its evidence and its reasoning, and report its verdict.",
        epilog=_exit_codes(
            (ExitCode.OK, "the justification holds, was skipped, or a dry run found it valid"),
            (
                ExitCode.FAILED,
                "it does not hold: an element failed, or --strict and one was skipped",
            ),
            (ExitCode.USAGE, "the command line is wrong; nothing ran"),
            (
                ExitCode.INVALID,
                "nothing ran: the justification was refused, a step library could not be "
                "imported, or validation reported an error",
            ),
            (
                ExitCode.IO,
                "a file could not be read or written, or Graphviz could not draw a diagram",
            ),
        ),
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
    run.add_argument(
        "--jobs",
        type=_jobs,
        default=1,
        metavar="N",
        help="run up to N steps at a time, each on a thread of its own, when the argument "
        "does not order them; auto runs one per CPU (default: 1)",
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
    outputs.add_argument(
        "--events",
        type=Path,
        metavar="PATH",
        help="write the run's events to PATH as the run goes, one JSON object per line, "
        "for a program that shows the run while it runs",
    )
    formats = ", ".join(diagram.FORMATS)
    outputs.add_argument(
        "--diagram",
        type=Path,
        metavar="PATH",
        help=f"draw the dataflow, with the run over it, to PATH: the justification, and the "
        f"files and variables its steps declare; the suffix of PATH is the format: {formats}",
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


def _jobs(text: str) -> int:
    """How many steps may run at a time: a positive integer, or ``auto``, one per CPU this
    process may use."""
    if text == "auto":
        # os.process_cpu_count, new in Python 3.13, counts only the CPUs the process may use.
        counted: int | None = getattr(os, "process_cpu_count", os.cpu_count)()
        return counted or 1
    jobs = int(text) if text.isdecimal() else 0
    if jobs < 1:
        raise argparse.ArgumentTypeError(f"expected a positive number or auto, not {text!r}")
    return jobs


def impact_parser() -> argparse.ArgumentParser:
    """The parser of ``jpipe-runner impact``."""
    parser = _Parser(
        prog=f"{_PROGRAM} impact",
        description="List the evidence that observes changed files, and every element "
        "above it, from what the step libraries declare. No step is called.",
        epilog=_exit_codes(
            (ExitCode.OK, "the analysis is listed, whatever the changes reach"),
            (ExitCode.USAGE, "the command line is wrong"),
            (
                ExitCode.INVALID,
                "the step libraries declare nothing to analyze: the justification was "
                "refused, or a step library could not be imported",
            ),
            (ExitCode.IO, "a file could not be read, or git could not list the changes"),
        ),
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
    parser.set_defaults(strict=False, dry_run=True, jobs=1)
    return parser


def status_parser() -> argparse.ArgumentParser:
    """The parser of ``jpipe-runner status``."""
    parser = _Parser(
        prog=f"{_PROGRAM} status",
        description="Compare what a run observed, as its JSON report recorded it, with "
        "what it is now, and list what is stale. No step is called.",
        epilog=_exit_codes(
            (ExitCode.OK, "nothing changed"),
            (ExitCode.FAILED, "something is stale, or needs a new run to be checked"),
            (ExitCode.USAGE, "the command line is wrong"),
            (ExitCode.INVALID, "the file is not the report of a run that observed files"),
            (ExitCode.IO, "the report cannot be read"),
        ),
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
    except _Stop as stop:  # --help, --version, or a usage error
        return stop.status
    with _logging(options.verbose, options.quiet):
        try:
            command.check(reader, options)
            return command.run(options)
        except _Stop as stop:  # a usage error the command's check found
            return stop.status
        except OSError as error:  # the check's too: a path it cannot even look at
            _log_error(error)
            return ExitCode.IO


def _check_outputs(command: argparse.ArgumentParser, options: argparse.Namespace) -> None:
    """Refuse, before anything runs, the outputs that could not be written, or that would
    overwrite what the run reads."""
    outputs = _outputs(options)
    read = {identity(library): "a step library" for library in _libraries(options.library)}
    read[identity(options.justification)] = "the justification"
    seen: dict[object, str] = {}
    for flag, path in outputs.items():
        if path is None:
            continue
        if path.is_dir():
            command.error(f"{flag} {path}: a directory, where a file is expected")
        suffix = path.suffix.removeprefix(".").lower()
        if flag == "--diagram" and suffix not in diagram.FORMATS:
            formats = ", ".join(diagram.FORMATS)
            command.error(f"{flag} {path}: the suffix of the file is its format, one of {formats}")
        written = identity(path)
        if (input_ := read.get(written)) is not None:
            command.error(f"{flag} {path}: {input_}, which the run reads")
        if (same := seen.get(written)) is not None:
            command.error(f"{same} and {flag} both write {path}")
        seen[written] = flag


def _outputs(options: argparse.Namespace) -> dict[str, Path | None]:
    """The files a run writes, by the option that names each."""
    return {"--report": options.report, "--events": options.events, "--diagram": options.diagram}


def _check_observed(
    outputs: dict[str, Path | None],
    justification: Justification,
    registry: StepRegistry,
    root: Path,
) -> None:
    """Refuse, once the step libraries are imported and before anything else runs, an
    output that designates a file a step bound to ``justification`` observes: the run would
    overwrite it, or read what it wrote there (ADR-0035)."""
    given = {flag: path for flag, path in outputs.items() if path is not None}
    if not given:
        return
    observed = [
        (binding.step.name, shown)
        for binding in BindingTable(justification, registry).bindings
        for shown in ElementReport.of(justification, binding.element, binding, root=root).observes
    ]
    for flag, path in given.items():
        if (found := _observing(observed, path, root)) is not None:
            observer, shown = found
            parser().error(f"{flag} {path}: {shown}, which {observer} observes")


def _run(options: argparse.Namespace) -> int:
    _check_graphviz(options.diagram)
    # The working directory, as a relative path: a step receives the files it observes
    # relative to it, as the report shows them, and a reason that names one reads the same
    # on every machine.
    root = Path()
    _LOG.info("steps run with Python %s, in %s", sys.executable, Path.cwd())
    # Expanded before the events file is opened, which a glob could otherwise match.
    libraries = _libraries(options.library)
    preview = None if options.events is None else _Preview(root)
    try:
        with _events(options.events, root, preview) as stream:

            def checked(justification: Justification, registry: StepRegistry) -> None:
                _check_observed(_outputs(options), justification, registry, root)
                if stream is not None:
                    stream.release()

            justification, report = _report(options, root, libraries, stream, checked)
            _LOG.info("verdict: %s", report.verdict)
            report, drawn = _draw(options, justification, report, root)
            saved = _save(options.report, report)
            ok = drawn and saved
            code = exit_code(report.verdict, strict=options.strict) if ok else ExitCode.IO
            _print(options, report)
            if stream is not None:
                # A stream that failed writes nothing more, so this exit code is never shown.
                stream.run_ended(report, code, options.report if saved else None)
    finally:
        # Once the run has ended, whatever ended it: the preview has had its use.
        if preview is not None:
            preview.discard()
    # Once the file is closed: closing it writes what it still holds, and may fail.
    return code if _streamed(stream) else ExitCode.IO


def _print(options: argparse.Namespace, report: RunReport) -> None:
    """Print the report on stdout: the JSON report with ``--json``, the text one otherwise."""
    if options.json:
        sys.stdout.write(json_report.dumps(report))
    else:
        colour = _colour(options.colour)
        unicode = text_report.use_unicode(sys.stdout)
        sys.stdout.write(text_report.render(report, colour=colour, unicode=unicode))
    sys.stdout.flush()


@contextmanager
def _events(
    path: Path | None, root: Path, preview: Preview | None = None
) -> Iterator[EventStream | None]:
    """The stream of the run's events, written to ``path``, if one is given, which draws
    the diagram with ``preview`` before the first step. A file that cannot be opened is an
    ``OSError``, before anything runs."""
    if path is None:
        yield None
        return
    created = _missing_directories(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    target = Path(os.path.realpath(path))  # what a link names, the file the run writes
    existed = target.exists()
    # A file that holds something other than a run's events may be one the run observes,
    # which is known only once the step libraries are imported: it is opened without being
    # emptied, and the stream holds its events until then (ADR-0035). Anything else, a new
    # file, a previous run's events, a pipe, is emptied and written at once, as ever; a
    # regular file's content is kept, to be put back if an output is refused.
    held = _foreign(path)
    kept = _kept(target) if existed and not held and target.is_file() else None
    file = path.open("a" if held else "w", encoding="utf-8", newline="\n")
    stream = EventStream(file, root=root, preview=preview, held=held)
    _LOG.info("writing the run's events to %s", path)
    refused = False
    try:
        yield stream
    except _Stop:  # an output names a file the run observes: leave it as it was
        refused = True
        raise
    finally:
        if not refused:
            # The run ended before the check, its model refused or a library not imported:
            # nothing tells whether a step would observe a file that holds something else.
            stream.abandon(
                f"{path} holds something other than a run's events, and the run ended "
                "before it could check that no step observes it"
            )
        stream.close()
        if refused:
            _put_back(target, kept, existed, created)
        if kept is not None:
            kept.unlink(missing_ok=True)


def _kept(target: Path) -> Path:
    """A copy of ``target``, in a temporary file of the system's temporary directory, to
    put back if an output is refused: the file may be large, so it is not kept in memory."""
    handle, copy = tempfile.mkstemp(prefix="jpipe-runner-events-")
    os.close(handle)
    shutil.copyfile(target, copy)
    return Path(copy)


def _put_back(target: Path, kept: Path | None, existed: bool, created: list[Path]) -> None:
    """Leave the events file of a refused run as it was: its ``kept`` copy put back, or, if
    the run ``created`` it, removed, with the directories made for it."""
    # The path is the --events option the user gave, which the run writes anyway: what it
    # puts back is that file's own content, and what it removes, the file it created.
    if kept is not None:
        shutil.copyfile(kept, target)  # NOSONAR
    elif not existed:
        target.unlink(missing_ok=True)  # NOSONAR
        for directory in created:
            with suppress(OSError):
                directory.rmdir()


def _missing_directories(directory: Path) -> list[Path]:
    """The directories ``mkdir(parents=True)`` would create for ``directory``, deepest
    first."""
    missing = []
    while not directory.exists() and directory != directory.parent:
        missing.append(directory)
        directory = directory.parent
    return missing


def _foreign(path: Path) -> bool:
    """Whether ``path`` is a regular file that holds something other than a run's events:
    not empty, and not beginning with a ``run.started`` event. One that cannot be read is
    taken for one."""
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        with path.open("rb") as file:
            return file.read(len(RUN_STARTED)) != RUN_STARTED
    except OSError:
        return True


class _Preview:
    """What draws the diagram before the first step, as a dry run would draw it, for a
    program that follows the run's events (ADR-0032): an SVG file in a directory of its own,
    in the system's temporary directory, which ``discard`` deletes when the run ends. The
    drawing is a preview: whatever keeps it from being drawn, Graphviz missing included, is
    logged, and changes nothing else. ``--diagram`` holds only the run's own diagram."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._directory: Path | None = None

    def __call__(self, planned: RunResult) -> Path | None:
        if shutil.which("dot") is None:
            _LOG.warning(
                "the diagram is not drawn before the steps run: Graphviz's dot is not "
                "installed, or not on the PATH"
            )
            return None
        try:
            self._directory = Path(tempfile.mkdtemp(prefix="jpipe-runner-")).absolute()
            drawn = self._directory / "diagram.svg"
            report = RunReport.of(planned, self._root)
            if observer := _observer(report, drawn, self._root):
                # A temporary directory in the project, as TMPDIR may make it.
                _LOG.warning(
                    "the diagram is not drawn before the steps run: %s, so the steps "
                    "could observe it at %s",
                    observer,
                    drawn,
                )
                self.discard()
                return None
            diagram.write(drawn, planned.justification, report)
        # Whatever went wrong, from an observable of the library that cannot describe
        # itself to dot, a preview never stops the run.
        except Exception as error:  # NOSONAR
            why = _reason(error) if isinstance(error, OSError) else f"{error!r}"
            _LOG.warning("cannot draw the diagram before the steps run: %s", why)
            return None
        _LOG.info("drew the diagram at %s, before the steps run", drawn)
        return drawn

    def discard(self) -> None:
        """Delete the drawing, and its directory, if it was drawn. On Windows, a file a
        program has open cannot be deleted, as the reader of the drawing may have it for a
        moment: try again, for about a second. What cannot be deleted is a warning."""
        if self._directory is None:
            return
        directory, self._directory = self._directory, None

        def remove() -> None:
            with suppress(FileNotFoundError):
                shutil.rmtree(directory)

        try:
            diagram.retried(remove, OSError)
        except OSError as error:
            _LOG.warning("cannot delete the diagram drawn before the steps run: %s", error)


def _observer(report: RunReport, drawn: Path, root: Path) -> str | None:
    """What an evidence observes that designates ``drawn``, if one does."""
    observed = [(element.id, shown) for element in report.elements for shown in element.observes]
    found = _observing(observed, drawn, root)
    return None if found is None else f"{found[0]} observes {found[1]}"


def _observing(
    observed: Iterable[tuple[str, str]], path: Path, root: Path
) -> tuple[str, str] | None:
    """The first of ``observed``, each who observes what, as the report shows it, that
    designates the file at ``path``, if one does (ADR-0035)."""
    return next(((who, shown) for who, shown in observed if designates(shown, path, root)), None)


def _streamed(stream: EventStream | None) -> bool:
    """Whether every event was written, if there is a stream."""
    return stream is None or not stream.failed


def _check_graphviz(path: Path | None) -> None:
    """Raise ``FileNotFoundError`` if the diagram needs Graphviz's ``dot``, and it is not
    installed: nothing should run for an output that cannot be drawn."""
    needed = path is not None and path.suffix.lower() != ".dot"
    if needed and shutil.which("dot") is None:
        raise FileNotFoundError(
            f"Graphviz's dot is needed to draw {path}, and is not installed or not on "
            "the PATH: install Graphviz (https://graphviz.org/download/), or draw a .dot file"
        )


def _report(
    options: argparse.Namespace,
    root: Path,
    libraries: list[Path],
    stream: EventStream | None = None,
    before_run: Callable[[Justification, StepRegistry], None] | None = None,
) -> tuple[Justification | None, RunReport]:
    """The model, unless it was refused, and the report of the run of ``libraries``,
    however it ended. ``stream``, if there is one, is told of the run as it goes, and
    ``before_run``, if given, is called once the libraries are imported, before the
    engine."""
    try:
        justification = loader.load(options.justification)
    except InvalidJustificationError as error:
        if stream is not None:
            stream.run_started(None, strict=options.strict, dry_run=options.dry_run)
        return None, RunReport.refused(error, strict=options.strict)
    if stream is not None:
        stream.run_started(justification, strict=options.strict, dry_run=options.dry_run)
    _LOG.info(
        "loaded %s from %s: %d elements",
        justification.name,
        options.justification,
        len(justification),
    )
    try:
        with _steps_write_on_stderr(), imported(libraries, options.python_path) as modules:
            _LOG.debug("sys.path: %s", sys.path)
            registry = StepRegistry.from_modules(modules)
            _LOG.info("step libraries imported: %d (%d steps)", len(modules), len(registry))
            if before_run is not None:
                before_run(justification, registry)
            result = engine.run(
                justification,
                registry,
                strict=options.strict,
                root=root,
                dry_run=options.dry_run,
                listener=stream,
                jobs=options.jobs,
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
    """The report, recording the diagram if it was drawn, and whether it was, if asked for."""
    path: Path | None = options.diagram
    if path is None:
        return report, True
    if justification is None:
        _LOG.warning("the model was refused, so %s is not drawn", path)
        return report, True
    try:
        diagram.write(path, justification, report)
    except OSError as error:
        _log_error(error)
        return report, False
    _LOG.info("drew the diagram at %s", path)
    return report.with_diagram(shown_path(str(path), root)), True


def _save(path: Path | None, report: RunReport) -> bool:
    """Write the JSON report to ``path``, if one is given; whether it was written."""
    if path is None:
        return True
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json_report.dumps(report), encoding="utf-8")
    except OSError as error:
        # An error is one line on stderr, not a traceback (ADR-0023).
        _LOG.error("cannot write the report to %s: %s", path, _reason(error))  # NOSONAR
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
    _, report = _report(options, Path(), _libraries(options.library))
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
    inside: list[str] = []
    for path in paths:
        shown = _under_working_directory(path)
        if shown is None:
            _LOG.warning("%s is outside the working directory, and is left out", path)
        else:
            inside.append(shown)
    return inside


def _under_working_directory(path: str) -> str | None:
    """``path`` relative to the working directory, as evidence declares it, or ``None``.

    ``.`` and ``..`` are resolved as text, so that a symbolic link under the working
    directory keeps its own path, as an evidence that observes it names it; a path that
    reaches the working directory through a link of its own is tried resolved."""
    here = Path.cwd()
    candidates = [Path(os.path.normpath(here / path)), Path(path).resolve()]
    for candidate in candidates:
        for base in (here, here.resolve()):
            if candidate.is_relative_to(base):
                return candidate.relative_to(base).as_posix()
    return None


def _status(options: argparse.Namespace) -> int:
    """Whether the files a run observed have changed since its report was written."""
    try:
        document = impact.read(options.report)
    except impact.InvalidReportError as error:
        # An error is one line on stderr, not a traceback (ADR-0023).
        _LOG.error("%s", error)  # NOSONAR
        return ExitCode.INVALID
    if document["verdict"] in (Verdict.INVALID, Verdict.VALID):
        _LOG.error(
            "%s is the report of a run in which no step ran: it observed no file", options.report
        )
        return ExitCode.INVALID
    changes = impact.stale(document)
    reached = {
        (e["id"], a["path"])
        for e in document["elements"]
        for a in e["artifacts"]
        if impact.sha256_read(a) is not None
    }
    vanished = {
        (change.element, change.path)
        for change in changes
        if change.kind is impact.ChangeKind.VANISHED
    }
    # Files only: an environment variable that is no longer set is no sign of a wrong root.
    if reached and reached <= vanished:
        _LOG.warning(
            "every file the run observed is missing: run status from the directory the run "
            "ran in, where the report's paths start"
        )
    unchecked = impact.unverified(document)
    sys.stdout.write(impact.render_stale(document, changes, unchecked))
    return ExitCode.FAILED if changes or unchecked else ExitCode.OK


def _colour(choice: str) -> bool:
    """Whether to colour the text report: ``always`` and ``never`` override ``NO_COLOR``."""
    if choice == "auto":
        return text_report.use_colour(sys.stdout, os.environ)
    return choice == "always"


def _log_error(error: OSError) -> None:
    """Log ``error`` as one line on stderr, not a traceback (ADR-0023)."""
    _LOG.error("%s", _reason(error))  # NOSONAR


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


@contextmanager
def _steps_write_on_stderr() -> Iterator[None]:
    """Send to stderr what the step libraries print, and what the programs they start
    write, while they are imported and run: stdout carries the report, and nothing else
    (ADR-0023)."""
    sys.stdout.flush()
    saved = _stdout_on_stderr()
    try:
        with redirect_stdout(sys.stderr):
            yield
    finally:
        sys.stderr.flush()
        if saved is not None:
            os.dup2(saved, 1)
            os.close(saved)


def _stdout_on_stderr() -> int | None:
    """Point file descriptor 1 at stderr, and return a copy of what it was, or ``None``
    when there is no stdout or stderr to point it at, and nothing was changed."""
    try:
        saved = os.dup(1)
    except OSError:
        return None
    try:
        os.dup2(2, 1)
    except OSError:
        os.close(saved)
        return None
    return saved


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
