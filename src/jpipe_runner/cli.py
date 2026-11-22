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
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import textwrap
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, redirect_stdout, suppress
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, NoReturn

from jpipe_runner import __version__, diagram, engine, impact, json_report, loader, text_report
from jpipe_runner.binding import BindingTable
from jpipe_runner.diagnostics import shown_path
from jpipe_runner.engine import RunResult, Verdict
from jpipe_runner.events import EventStream, Preview
from jpipe_runner.libraries import LibraryLoadError, imported
from jpipe_runner.model import InvalidJustificationError, Justification
from jpipe_runner.observables import (
    Context,
    dependencies,
    designates_one,
    files,
    is_glob,
    matches,
    unescape,
)
from jpipe_runner.report import RunReport
from jpipe_runner.steps import StepRegistry

_WINDOWS = os.name == "nt"

_FIRST_LINE = 1 << 16
"""How much of an existing events file is read to tell a run's events from anything else."""
_ATTEMPTS, _PAUSE = 10, 0.1
"""How many times, and how far apart in seconds, the drawing made before the steps is
deleted."""

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
    parser.set_defaults(strict=False, dry_run=True)
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
    outputs = {
        "--report": options.report,
        "--events": options.events,
        "--diagram": options.diagram,
    }
    read = {_identity(library): "a step library" for library in _libraries(options.library)}
    read[_identity(options.justification)] = "the justification"
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
        identity = _identity(path)
        if (input_ := read.get(identity)) is not None:
            command.error(f"{flag} {path}: {input_}, which the run reads")
        if (same := seen.get(identity)) is not None:
            command.error(f"{same} and {flag} both write {path}")
        seen[identity] = flag


def _check_observed(
    options: argparse.Namespace, justification: Justification, registry: StepRegistry, root: Path
) -> None:
    """Refuse, once the step libraries are imported and before anything else runs, an
    output that names a file a step bound to ``justification`` observes: one it names, one
    its glob matches, or one a library's observable depends on. The run would overwrite it,
    or read what it wrote there (ADR-0035)."""
    outputs = {  # impact, which shares the import, writes none
        "--report": getattr(options, "report", None),
        "--events": getattr(options, "events", None),
        "--diagram": getattr(options, "diagram", None),
    }
    if all(path is None for path in outputs.values()):
        return
    observed = [
        (shown, f"{binding.step.name} observes")
        for binding in BindingTable(justification, registry).bindings
        for artifact in binding.step.observes
        for shown in dependencies(artifact.observable, Context(binding.step.directory, root))
    ]
    collisions = _Collisions(observed, root)
    for flag, path in outputs.items():
        if path is not None and (found := collisions.of(path)) is not None:
            shown, who = found
            parser().error(f"{flag} {path}: {shown}, which {who}")


class _Collisions:
    """Whether a file is one of ``observed``, each a path or a glob relative to ``root`` as
    the report shows it, with who observes it: by its name, once resolved under ``root``,
    even if it does not exist yet, or as a link to a file a glob matches. Each glob is
    expanded once."""

    def __init__(self, observed: list[tuple[str, str]], root: Path) -> None:
        self._observed = observed
        self._root = root
        self._matched: dict[str, set[object]] = {}

    def of(self, path: Path) -> tuple[str, str] | None:
        """The first of the observed that designates ``path``, if one does."""
        identity = _identity(path)
        relative = _under(path, self._root)
        for shown, who in self._observed:
            if designates_one(shown):
                if identity == _identity(self._root / unescape(shown)):
                    return shown, who
            elif (relative is not None and matches(relative, shown)) or identity in self._found(
                shown
            ):
                return shown, who
        return None

    def _found(self, pattern: str) -> set[object]:
        if pattern not in self._matched:
            self._matched[pattern] = {_identity(found) for found in files(pattern, self._root)}
        return self._matched[pattern]


def _under(path: Path, root: Path) -> str | None:
    """``path`` relative to ``root``, in POSIX form, once both are resolved, so that a
    directory reached through a link is the one it links to; ``None`` if it is not under
    ``root``, on another drive included."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def _identity(path: Path) -> object:
    """What tells ``path``'s file from any other: its device and its inode if it exists,
    so that a link is the file it links to, and its absolute path otherwise."""
    try:
        status = path.stat()
    except OSError:
        return path.resolve()
    # A file system that has no inodes gives 0 for every file.
    return (status.st_dev, status.st_ino) if status.st_ino else path.resolve()


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
            justification, report = _report(options, root, libraries, stream)
            if stream is not None and stream.held:
                # The model was refused, or a library not imported: nothing tells whether
                # the run would observe the file, so it is left as it was.
                stream.abandon(
                    f"{options.events} holds something other than a run's events, and the "
                    "run ended before it could check that no step observes it"
                )
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
    existed = os.path.lexists(path)
    # A file that holds something other than a run's events may be one the run observes,
    # which is known only once the step libraries are imported: it is opened without being
    # emptied, and the stream holds its events until then (ADR-0035). Anything else, a new
    # file, a previous run's events, a pipe, is emptied and written at once, as ever.
    held = _foreign(path)
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
        stream.close()
        if refused and not existed:
            path.unlink(missing_ok=True)
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
    not empty, and its first line not a ``run.started`` event. One that cannot be read is
    taken for one."""
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return False
        with path.open("rb") as file:
            first = json.loads(file.readline(_FIRST_LINE))
    except (OSError, ValueError):
        return True
    return not (isinstance(first, dict) and first.get("event") == "run.started")


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
        for attempt in range(_ATTEMPTS):
            try:
                shutil.rmtree(directory)
                return
            except FileNotFoundError:
                return
            except OSError as error:
                if _WINDOWS and attempt < _ATTEMPTS - 1:
                    time.sleep(_PAUSE)
                    continue
                _LOG.warning("cannot delete the diagram drawn before the steps run: %s", error)
                return


def _observer(report: RunReport, drawn: Path, root: Path) -> str | None:
    """What an evidence observes that designates ``drawn``, if one does."""
    observed = [
        (shown, f"{element.id} observes")
        for element in report.elements
        for shown in element.observes
    ]
    found = _Collisions(observed, root).of(drawn)
    return None if found is None else f"{found[1]} {found[0]}"


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
) -> tuple[Justification | None, RunReport]:
    """The model, unless it was refused, and the report of the run of ``libraries``,
    however it ended. ``stream``, if there is one, is told of the run as it goes."""
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
            _check_observed(options, justification, registry, root)
            if stream is not None:
                stream.release()
            result = engine.run(
                justification,
                registry,
                strict=options.strict,
                root=root,
                dry_run=options.dry_run,
                listener=stream,
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
