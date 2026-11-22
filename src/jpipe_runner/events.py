"""The events of a run: what the runner tells a program while the run goes on (ADR-0030).

``jpipe-runner --events PATH`` writes them to ``PATH``, one JSON object per line (JSON
Lines), each flushed as it is written, for a program that follows the file to show the run
as it goes, such as the IDE. ``events.schema.json``, shipped in the package, describes them:

- ``run.started``, once the model is read or refused: every element's id;
- ``validation.ended``, with what validation reported;
- ``diagram.drawn``, when the run's diagram was drawn before the first step, as a dry run
  would draw it, in a temporary file, for a program that colours it as the run goes
  (ADR-0032);
- ``element.started``, when an element's step is about to be called;
- ``source.observed``, for each source an evidence observes, once it is observed and
  before its step is called: whether it was reached;
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
from jpipe_runner.engine import ElementResult, RunResult
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


Preview = Callable[[RunResult], Path | None]
"""What draws a run's diagram before its first step, from the result a dry run would have
returned: where it drew it, or ``None`` if it could not."""


class EventStream:
    """A run's events, written to ``file`` as they happen. It is the engine's
    ``RunListener``, and the command line tells it when the run starts and ends.

    ``preview``, if given, is asked to draw the run's diagram once the steps are about to
    run; the stream says where it was drawn, if it was.

    A ``held`` stream keeps its events until ``release``, which empties the file first, or
    ``abandon``, which writes none: the command line holds a file that holds something
    other than a run's events until it has checked that no step observes it (ADR-0035).
    """

    def __init__(
        self,
        file: TextIO,
        *,
        root: Path = Path(),
        clock: Callable[[], float] = time.monotonic,
        preview: Preview | None = None,
        held: bool = False,
    ) -> None:
        self._file = file
        self._held: list[str] | None = [] if held else None
        self._root = root
        self._clock = clock
        self._preview = preview
        self._opened = clock()
        self._seq = 0
        self._model: Justification | None = None
        self._failed = False

    def release(self) -> None:
        """Empty the file, and write the events held so far; from now on, each is written as
        it happens. A stream that is not held is left as it is."""
        if self._held is None:
            return
        lines, self._held = self._held, None
        try:
            self._file.truncate(0)
            self._file.seek(0)
            for line in lines:
                self._file.write(line)
            self._file.flush()
        except OSError as error:
            self._fail(error.strerror or str(error))

    def abandon(self, reason: str) -> None:
        """Write none of the events of a held stream, and leave the file as it was: the
        stream has failed, for ``reason``, which is logged. A stream that is not held is
        left as it is."""
        if self._held is None:
            return
        self._held = None
        self._fail(reason)

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

    def steps_starting(self, planned: RunResult) -> None:
        if self._preview is None or self._failed:
            return
        drawn = self._preview(planned)
        if drawn is not None:
            # Absolute, unlike the report's paths: the drawing is not the run's, and a program
            # that runs elsewhere must find it.
            self._write("diagram.drawn", path=str(drawn.absolute()))

    def element_started(self, element: Element) -> None:
        self._write("element.started", id=element.id)

    def source_observed(self, element: Element, source: str, reachable: bool) -> None:
        self._write("source.observed", id=element.id, source=source, reachable=reachable)

    def element_decided(self, result: ElementResult) -> None:
        if self._model is None:
            raise RuntimeError("an element was decided before the run started: a runner bug")
        reported = ElementReport.of(
            self._model, result.element, result.binding, result, self._root, result.inputs
        )
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

    def close(self) -> None:
        """Close the file. Closing writes what the file still holds, and may fail too."""
        try:
            self._file.close()
        except OSError as error:
            self._fail(error.strerror or str(error))

    def _write(self, event: str, **payload: Any) -> None:
        if self._failed:
            return
        elapsed = max(0, round((self._clock() - self._opened) * 1000))
        line = {"event": event, "seq": self._seq, "elapsed_ms": elapsed, **payload}
        text = _one_line(json.dumps(line, ensure_ascii=False)) + "\n"
        if self._held is not None:
            self._held.append(text)
        else:
            try:
                self._file.write(text)
                self._file.flush()
            except OSError as error:
                self._fail(error.strerror or str(error))
                return
        self._seq += 1

    def _fail(self, reason: str) -> None:
        """Nothing more is written: the first error is logged, and only the first."""
        if not self._failed:
            # An error is one line on stderr, not a traceback (ADR-0023).
            _LOG.error("cannot write the run's events: %s", reason)  # NOSONAR
        self._failed = True


def _one_line(text: str) -> str:
    """``text``, JSON, with the characters ``_ESCAPED`` names escaped as JSON escapes them."""
    return _ESCAPED.sub(lambda found: f"\\u{ord(found[0]):04x}", text)
