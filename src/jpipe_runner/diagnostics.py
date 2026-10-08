"""Diagnostics: what the runner reports about a model, a step library or a run.

A diagnostic is data. Its ``code`` is the contract that tests, reports and users rely on;
its ``message`` is written for humans and may be reworded at any time. Severity is real
(#118). An ``ERROR`` in loading or validation stops the run before any step executes;
while the steps run, an ``ERROR`` fails the element it is about, and the run goes on. A
``WARNING`` is reported and changes nothing else.
"""

from dataclasses import dataclass
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


def _in_user_code(frame: FrameSummary) -> bool:
    if frame.filename.startswith("<frozen importlib"):
        return False
    return not Path(frame.filename).resolve().is_relative_to(_PACKAGE)
