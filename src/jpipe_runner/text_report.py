"""The text report: a run as a person reads it in a terminal, in the manner of Cucumber.

Each element is a line, in the order run: a symbol for its status, its kind, its label,
and its id as a comment. An element that did not pass says why underneath, and a failed
evidence names the files it observed. Then come the diagnostics, each with its fix and,
for an exception, its traceback; then the summary, and the verdict last.

The layout is not a contract, and may change in any release: scripts read the JSON report.
``render`` is a pure function of the report. Whether to colour it, and whether the
terminal can show its symbols, is decided by the caller, with ``use_colour`` and
``use_unicode``.
"""

from collections.abc import Iterator, Mapping
from typing import TextIO

from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.engine import Status, Verdict
from jpipe_runner.model import Kind
from jpipe_runner.report import ElementReport, RunReport, Trace

_SYMBOLS = {Status.PASS: "✔", Status.FAIL: "✘", Status.SKIP: "-"}
_ASCII_SYMBOLS = {Status.PASS: "+", Status.FAIL: "x", Status.SKIP: "-"}

# ANSI colours: green, red, cyan as Cucumber has them, and yellow for warnings.
_GREEN, _RED, _CYAN, _YELLOW = "32", "31", "36", "33"
_STATUS_COLOURS = {Status.PASS: _GREEN, Status.FAIL: _RED, Status.SKIP: _CYAN}
_VERDICT_COLOURS = {
    Verdict.PASS: _GREEN,
    Verdict.FAIL: _RED,
    Verdict.SKIP: _CYAN,
    Verdict.INVALID: _RED,
    Verdict.VALID: _GREEN,
}
_SEVERITY_COLOURS = {Severity.ERROR: _RED, Severity.WARNING: _YELLOW}

_INDENT = "  "
_DETAIL = "      "
_LABEL_WIDTH = 50
"""Labels are padded to align the ids, up to this width; a longer label pushes its id."""


def render(report: RunReport, *, colour: bool = False, unicode: bool = True) -> str:
    """``report`` as text. ``colour`` adds ANSI colours; without ``unicode``, the symbols
    and the ellipsis are written in ASCII."""
    return "\n".join(_Text(report, colour, unicode).lines()) + "\n"


def use_colour(stream: TextIO, environ: Mapping[str, str]) -> bool:
    """Whether to colour what is written to ``stream``: when it is a terminal, unless
    ``NO_COLOR`` is set to anything but the empty string (https://no-color.org)."""
    if environ.get("NO_COLOR"):
        return False
    try:
        return stream.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def use_unicode(stream: TextIO) -> bool:
    """Whether ``stream``'s encoding can write the report's symbols."""
    try:
        "".join(_SYMBOLS.values()).encode(getattr(stream, "encoding", None) or "ascii")
    except (UnicodeEncodeError, LookupError):
        return False
    return True


class _Text:
    """The lines of one report, rendered with one set of options."""

    def __init__(self, report: RunReport, colour: bool, unicode: bool) -> None:
        self._report = report
        self._colour = colour
        self._symbols = _SYMBOLS if unicode else _ASCII_SYMBOLS
        self._ellipsis = "…" if unicode else "..."

    def lines(self) -> Iterator[str]:
        for section in (self._header(), self._elements(), self._diagnostics()):
            block = list(section)
            if block:
                yield from block
                yield ""
        yield from self._summary()

    def _header(self) -> Iterator[str]:
        if self._report.justification is None:
            return
        yield f"Justification: {self._report.justification}"
        for element in self._report.elements:
            if element.kind is Kind.CONCLUSION:
                yield f"{_INDENT}{element.label}"

    def _elements(self) -> Iterator[str]:
        shown = [(e, e.status) for e in self._report.elements if e.status is not None]
        if not shown:
            return
        kinds = max(len(_keyword(element.kind)) for element, _ in shown)
        labels = min(max(len(element.label) for element, _ in shown), _LABEL_WIDTH)
        for element, status in shown:
            line = f"{_INDENT}{self._symbols[status]} {_keyword(element.kind):<{kinds}}  "
            line += f"{element.label:<{labels}}  # {element.id}"
            colour = _STATUS_COLOURS[status]
            yield self._paint(line, colour)
            for detail in self._details(element):
                yield self._paint(f"{_DETAIL}{detail}", colour)

    def _details(self, element: ElementReport) -> Iterator[str]:
        if element.status is Status.PASS:
            return
        reason = element.reason or "no reason given"
        yield f"{element.step}: {reason}" if element.step and not element.blocked_by else reason
        if element.status is Status.FAIL:
            for artifact in element.artifacts:
                if artifact.reachable:
                    digest = f"sha256 {(artifact.sha256 or '')[:12]}{self._ellipsis}"
                    yield f"observed {artifact.path} ({digest}, {artifact.size} bytes)"
                else:
                    yield f"observed {artifact.path} (unreachable)"

    def _diagnostics(self) -> Iterator[str]:
        for diagnostic in self._report.diagnostics:
            yield self._paint(str(diagnostic), _SEVERITY_COLOURS.get(diagnostic.severity))
            if diagnostic.fix:
                yield f"{_INDENT}fix: {diagnostic.fix}"
            yield from self._traceback(diagnostic)

    def _traceback(self, diagnostic: Diagnostic) -> Iterator[str]:
        trace = self._report.trace(diagnostic)
        while trace is not None:
            yield from (f"{_INDENT}{line}" for line in _formatted(trace))
            trace = trace.cause
            if trace is not None:
                yield f"{_INDENT}Caused by:"

    def _summary(self) -> Iterator[str]:
        summary = self._report.summary
        if self._report.ran:
            counts = _counted(
                (summary.failed, "failed"), (summary.skipped, "skipped"), (summary.passed, "passed")
            )
            yield f"{_plural(summary.elements, 'element')} ({counts})"
        if self._report.diagnostics:
            counts = _counted(
                (summary.errors, _plural(summary.errors, "error", number=False)),
                (summary.warnings, _plural(summary.warnings, "warning", number=False)),
            )
            yield f"{_plural(len(self._report.diagnostics), 'diagnostic')} ({counts})"
        if self._report.strict:
            yield "strict: warnings count as errors"
        for view, path in (("diagram", self._report.diagram), ("dataflow", self._report.dataflow)):
            if path is not None:
                yield f"{view}: {path}"
        verdict = f"verdict: {self._report.verdict}"
        if self._report.verdict is Verdict.VALID:
            verdict += " (a dry run: no step was called)"
        elif not self._report.ran:
            verdict += " (nothing ran)"
        yield self._paint(verdict, _VERDICT_COLOURS[self._report.verdict])

    def _paint(self, text: str, colour: str | None) -> str:
        if not self._colour or colour is None:
            return text
        return f"\033[{colour}m{text}\033[0m"


def _keyword(kind: Kind) -> str:
    return kind.value.capitalize()


def _formatted(trace: Trace) -> Iterator[str]:
    """``trace`` as Python prints a traceback, from the frames the report keeps."""
    if trace.frames:
        yield "Traceback (most recent call last):"
    for frame in trace.frames:
        yield f'  File "{frame.file}", line {frame.line}, in {frame.function}'
        if frame.code:
            yield f"    {frame.code}"
    yield f"{trace.exception}: {trace.message}" if trace.message else trace.exception


def _counted(*counts: tuple[int, str]) -> str:
    """The counts that are not zero, such as ``1 failed, 2 passed``."""
    return ", ".join(f"{count} {what}" for count, what in counts if count)


def _plural(count: int, noun: str, *, number: bool = True) -> str:
    word = noun if count == 1 else f"{noun}s"
    return f"{count} {word}" if number else word
