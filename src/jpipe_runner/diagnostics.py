"""Diagnostics: what the runner reports about a model, a step library or a run.

A diagnostic is data. Its ``code`` is the contract that tests, reports and users rely on;
its ``message`` is written for humans and may be reworded at any time. A diagnostic about
an exception carries its traceback. Severity is real
(#118). An ``ERROR`` in loading or validation stops the run before any step executes;
while the steps run, an ``ERROR`` fails the element it is about, and the run goes on. A
``WARNING`` is reported and changes nothing else.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from traceback import FrameSummary, StackSummary, TracebackException

_PACKAGE = Path(__file__).resolve().parent


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    element: str | None = None
    """The id of the element the diagnostic is about, if it is about one."""
    fix: str | None = None
    """What to do about it, when there is something specific to say."""
    traceback: TracebackException | None = field(default=None, compare=False, repr=False)
    """The exception behind it, when there is one: a step that raised (``JP022``), a library
    that failed to import (``JP020``). Trimmed to the user's frames by ``user_traceback``.
    It is not part of what makes two diagnostics equal."""

    def __str__(self) -> str:
        where = f" [{self.element}]" if self.element else ""
        return f"{self.code} {self.severity}{where}: {self.message}"


def user_traceback(error: BaseException) -> TracebackException:
    """``error``'s traceback, as the author of a step library needs it.

    The frames of the runner and of ``importlib`` are left out, so the traceback starts in
    the library: what remains is where the author can act. It is kept structured, frame
    by frame, and holds no reference to the frames' variables.
    """
    trace = TracebackException.from_exception(error)
    trace.stack = StackSummary.from_list([f for f in trace.stack if _in_user_code(f)])
    return trace


def shown_path(filename: str, root: Path) -> str:
    """``filename`` as a report shows it: relative to ``root`` in POSIX form when it is a file
    under ``root``, so that it reads the same on every machine; unchanged otherwise."""
    if filename.startswith("<"):  # <string>, <frozen importlib._bootstrap>: not a file
        return filename
    try:
        return Path(filename).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return filename


def _in_user_code(frame: FrameSummary) -> bool:
    if frame.filename.startswith("<frozen importlib"):
        return False
    return not Path(frame.filename).resolve().is_relative_to(_PACKAGE)
