"""Diagnostics: what the runner reports about a model, a step library or a run.

A diagnostic is data. Its ``code`` is the contract that tests, reports and users rely on;
its ``message`` is written for humans and may be reworded at any time. Severity is real:
an ``ERROR`` stops the run, a ``WARNING`` is reported and the run continues (#118).
"""

from dataclasses import dataclass
from enum import StrEnum


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
