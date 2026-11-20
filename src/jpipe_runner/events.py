"""The events of a run: what the runner tells a program while the run goes on (ADR-0030).

``jpipe-runner --events PATH`` writes them to ``PATH``, one JSON object per line (JSON
Lines), each flushed as it is written, for a program that follows the file to show the run
as it goes, such as the IDE. ``events.schema.json``, shipped in the package, describes them:

- ``run.started``, once the model is read or refused: every element's id;
- ``validation.ended``, with what validation reported;
- ``element.started``, when an element's step is about to be called;
- ``element.decided``, when an element is decided, as the report will write it;
- ``run.ended``, last, with the verdict, the exit code and where the report is.

The events preview the JSON report, which stays the authority. Their order is causal: an
element is decided after every element that supports it, and one element's events may
come between another's. ``seq`` numbers them, and ``elapsed_ms`` says when each was
written, so, unlike the report, they are not deterministic.

A stream that cannot be written does not stop the run: the first error is logged, nothing
more is written, and ``failed`` says so, for the command line to exit with code 4.
"""

import json
import logging
import re
import time
from collections.abc import Callable, Iterable
from importlib.resources import files
from pathlib import Path
from typing import Any, TextIO

from jpipe_runner import json_report
from jpipe_runner.diagnostics import Diagnostic, shown_path
from jpipe_runner.engine import ElementResult
from jpipe_runner.model import Element, Justification
from jpipe_runner.report import ElementReport, RunReport
from jpipe_runner.validation import ValidationReport

SCHEMA_VERSION = "1.0"

SCHEMA: dict[str, Any] = json.loads(
    files("jpipe_runner").joinpath("schema/events.schema.json").read_text(encoding="utf-8")
)

_LOG = logging.getLogger(__name__)

_ESCAPED = re.compile("[\x85\u2028\u2029\ud800-\udfff]")
"""What JSON leaves as it is but a line of UTF-8 cannot hold: the characters that end a line
for some readers, such as Python's ``splitlines``, and a lone surrogate, which a file name
that is not UTF-8 decodes to. Escaped, an event is one line however its reader splits, and
it can always be written."""


class EventStream:
    """A run's events, written to ``file`` as they happen. It is the engine's
    ``RunListener``, and the command line tells it when the run starts and ends."""

    def __init__(
        self,
        file: TextIO,
        *,
        root: Path = Path(),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._file = file
        self._root = root
        self._clock = clock
        self._opened = clock()
        self._seq = 0
        self._model: Justification | None = None
        self._failed = False

    @property
    def failed(self) -> bool:
        """Whether an event could not be written: none was written after it."""
        return self._failed

    def run_started(
        self, justification: Justification | None, *, strict: bool, dry_run: bool
    ) -> None:
        """The model was read, or refused (``None``): nothing else has happened yet."""
        self._model = justification
        elements = () if justification is None else justification.topological_order()
        self._write(
            "run.started",
            schema_version=SCHEMA_VERSION,
            report_schema_version=json_report.SCHEMA_VERSION,
            justification=None if justification is None else justification.name,
            elements=[element.id for element in elements],
            strict=strict,
            dry_run=dry_run,
        )

    def validation_ended(self, report: ValidationReport) -> None:
        self._write(
            "validation.ended",
            passed=report.passed,
            diagnostics=self._diagnostics(report.diagnostics),
        )

    def element_started(self, element: Element) -> None:
        self._write("element.started", id=element.id)

    def element_decided(self, result: ElementResult) -> None:
        if self._model is None:
            raise RuntimeError("an element was decided before the run started: a runner bug")
        reported = ElementReport.of(self._model, result.element, result.binding, result, self._root)
        self._write(
            "element.decided",
            element=json_report.element(reported, self._root),
            diagnostics=self._diagnostics(result.diagnostics),
        )

    def run_ended(self, report: RunReport, exit_code: int, written: Path | None) -> None:
        """The run is over, and it exits with ``exit_code``: ``report`` is its report, and
        ``written`` where the JSON report was written, if it was."""
        self._write(
            "run.ended",
            verdict=str(report.verdict),
            exit_code=exit_code,
            summary=json_report.summary(report.summary),
            report=None if written is None else shown_path(str(written), self._root),
            diagram=report.diagram,
        )

    def _diagnostics(self, diagnostics: Iterable[Diagnostic]) -> list[dict[str, Any]]:
        return [json_report.diagnostic(each, self._root) for each in diagnostics]

    def _write(self, event: str, **payload: Any) -> None:
        if self._failed:
            return
        elapsed = max(0, round((self._clock() - self._opened) * 1000))
        line = {"event": event, "seq": self._seq, "elapsed_ms": elapsed, **payload}
        try:
            self._file.write(_one_line(json.dumps(line, ensure_ascii=False)) + "\n")
            self._file.flush()
        except OSError as error:
            self._failed = True
            _LOG.error("cannot write the run's events: %s", error.strerror or error)
            return
        self._seq += 1


def _one_line(text: str) -> str:
    """``text``, JSON, with the characters ``_ESCAPED`` names escaped as JSON escapes them."""
    return _ESCAPED.sub(lambda found: f"\\u{ord(found[0]):04x}", text)
