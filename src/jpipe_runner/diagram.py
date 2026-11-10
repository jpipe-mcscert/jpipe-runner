"""Diagrams: a justification drawn as the jPipe compiler draws it, with what a run concluded
(ADR-0022).

``source(justification, report)`` is the Graphviz DOT text of the diagram, and ``write``
renders it to a file. Without a report, or for a run in which nothing ran, the diagram is
the compiler's own (``jpipe process -f DOT``, jPipe 2.5.0): the same ids, labels wrapped at
40 characters, shapes and colours (the Okabe-Ito palette). A run's statuses are drawn over
it, in the same palette:

- **pass**: the compiler's node, with a green border;
- **fail**: filled vermillion, in white bold text;
- **skip**: filled light grey, with a dashed grey border, thicker when it is a root cause.

An edge takes the colour of the status of the element it comes from. In SVG, a node's
tooltip gives its status and reason.

The **dataflow** view adds what the steps declare: each file or glob an evidence observes,
and each variable a step produces or consumes, as nodes linked to the elements. A variable
without a producer or a consumer, or with several producers, and a file that could not be
reached, are drawn in vermillion.

Rendering pipes the DOT text to Graphviz's ``dot``, as the compiler does: only the binary
is needed. The ``dot`` format is the text itself, written without it.
"""

import fnmatch
import re
import subprocess
from collections.abc import Iterable, Iterator
from enum import StrEnum
from pathlib import Path

from jpipe_runner.engine import Status
from jpipe_runner.model import Element, Justification, Kind
from jpipe_runner.report import ElementReport, RunReport

FORMATS = ("dot", "gif", "jpeg", "jpg", "pdf", "png", "svg")

_WRAP_WIDTH = 40

# The compiler's node styles (DotNodeStyle, jPipe 2.5.0): shape, style, fill, border.
_KIND_STYLES: dict[Kind, dict[str, str]] = {
    Kind.CONCLUSION: {"shape": "rect", "style": "filled,rounded", "fillcolor": "lightgrey"},
    Kind.SUB_CONCLUSION: {"shape": "rect", "color": "#0072B2"},
    Kind.STRATEGY: {"shape": "hexagon", "style": "filled", "fillcolor": "#F0C27F"},
    Kind.EVIDENCE: {"shape": "note", "style": "filled", "fillcolor": "#9ECAE1"},
}

# The status overlay, in the compiler's Okabe-Ito palette.
_GREEN, _VERMILLION, _GREY, _LIGHT_GREY = "#009E73", "#D55E00", "#999999", "#EEEEEE"
_BLUE = "#0072B2"
_EDGE_COLOURS = {Status.PASS: _GREEN, Status.FAIL: _VERMILLION, Status.SKIP: _GREY}
_DATA = {"fontname": "Courier", "fontsize": "10"}

_BARE = re.compile(r"[A-Za-z_]\w*|\d+", re.ASCII)
"""What DOT accepts unquoted, of the values a diagram uses: a name, or a whole number."""
_INDENT = "  "


class View(StrEnum):
    """What a diagram shows."""

    JUSTIFICATION = "justification"
    """The argument: its elements and what supports what."""
    DATAFLOW = "dataflow"
    """The argument, and the files and variables its steps declare."""


def source(
    justification: Justification,
    report: RunReport | None = None,
    *,
    view: View = View.JUSTIFICATION,
) -> str:
    """The DOT text of the diagram of ``justification``, with what ``report`` concluded.

    The diagram is drawn from the model, whose order of elements and relations the
    compiler's drawing follows, so ``report`` must be a report of that model: raises
    ``ValueError`` if its elements, or what each supports, differ from the model's.
    """
    if report is not None:
        _check_reports_on(report, justification)
    reported = {} if report is None else {e.id: e for e in report.elements}
    return "".join(f"{line}\n" for line in _Diagram(justification, reported, view).lines())


def _check_reports_on(report: RunReport, model: Justification) -> None:
    """Raise ``ValueError`` unless ``report`` is a report of ``model``."""
    reported = {element.id: element.supports for element in report.elements}
    expected = {e.id: tuple(s.id for s in model.supported(e.id)) for e in model}
    if report.justification != model.name or reported != expected:
        raise ValueError(
            f"the report of {report.justification!r} is not a report of the model "
            f"{model.name!r}: their elements, or what supports what, differ"
        )


def write(
    path: Path,
    justification: Justification,
    report: RunReport | None = None,
    *,
    view: View = View.JUSTIFICATION,
    fmt: str | None = None,
) -> Path:
    """Write the diagram to ``path``, in ``fmt``, by default its suffix, and return ``path``.

    The directory is created if it does not exist. Raises ``ValueError`` for a format not
    in ``FORMATS``, ``FileNotFoundError`` if Graphviz's ``dot`` is not installed, and
    ``OSError`` if it fails.
    """
    fmt = (fmt or path.suffix.removeprefix(".")).lower()
    if fmt not in FORMATS:
        raise ValueError(f"a diagram is one of {', '.join(FORMATS)}, not {fmt!r}")
    text = source(justification, report, view=view)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "dot":
        path.write_text(text, encoding="utf-8")
        return path
    try:
        rendered = subprocess.run(
            ["dot", f"-T{fmt}", "-o", str(path)],
            input=text,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        raise FileNotFoundError(
            "Graphviz's dot is not installed, or not on the PATH: install Graphviz "
            "(https://graphviz.org/download/) to draw diagrams"
        ) from None
    if rendered.returncode != 0:
        raise OSError(f"dot failed to draw {path}: {rendered.stderr.strip()}")
    return path


class _Diagram:
    """The DOT lines of one diagram."""

    def __init__(
        self, model: Justification, reported: dict[str, ElementReport], view: View
    ) -> None:
        self._model = model
        self._reported = reported
        self._view = view

    def lines(self) -> Iterator[str]:
        label = (
            self._model.name
            if self._view is View.JUSTIFICATION
            else f"{self._model.name} ({self._view})"
        )
        yield f"digraph {_quoted(self._model.name)} {{"
        yield f"{_INDENT}rankdir=BT;"
        yield f"{_INDENT}label={_wrapped(label)};"
        for element in self._model:
            yield self._node(element)
        if self._view is View.DATAFLOW:
            yield from _Dataflow(self._reported).nodes()
        for relation in self._model.relations:
            yield self._edge(relation.source, relation.target)
        if self._view is View.DATAFLOW:
            yield from _Dataflow(self._reported).edges()
        yield "}"

    def _node(self, element: Element) -> str:
        reported = self._reported.get(element.id)
        attributes = dict(_KIND_STYLES[element.kind])
        if reported is not None and reported.status is not None:
            attributes.update(_overlay(attributes, reported))
        head = f"label={_wrapped(element.label)}, id={_quoted(element.id)}"
        return f"{_INDENT}{_quoted(element.id)} [{head}, {_attributes(attributes)}];"

    def _edge(self, source: str, target: str) -> str:
        reported = self._reported.get(source)
        status = None if reported is None else reported.status
        edge = f"{_INDENT}{_quoted(source)} -> {_quoted(target)}"
        if status is None:
            return f"{edge};"
        attributes = {"color": _EDGE_COLOURS[status]}
        if status is Status.SKIP:
            attributes["style"] = "dashed"
        return f"{edge} [{_attributes(attributes)}];"


class _Dataflow:
    """The files and variables a run's steps declare, as nodes and edges."""

    def __init__(self, reported: dict[str, ElementReport]) -> None:
        self._elements = list(reported.values())
        self._ran = any(element.status is not None for element in self._elements)

    def nodes(self) -> Iterator[str]:
        for path in _unique(p for e in self._elements for p in e.observes):
            attributes = dict(_DATA, shape="folder")
            if self._unreachable(path):
                attributes.update(color=_VERMILLION, penwidth="2")
            yield _data_node(f"artifact {path}", path, attributes)
        for name in self._variables():
            yield _data_node(f"variable {name}", name, self._variable(name))

    def edges(self) -> Iterator[str]:
        for element in self._elements:
            for path in element.observes:
                yield _data_edge(f"artifact {path}", element.id, "observes", dotted=True)
            for name in element.produces:
                yield _data_edge(element.id, f"variable {name}", "produces")
            for name in element.consumes:
                yield _data_edge(f"variable {name}", element.id, "consumes")

    def _variables(self) -> list[str]:
        return _unique(n for e in self._elements for n in (*e.produces, *e.consumes))

    def _variable(self, name: str) -> dict[str, str]:
        attributes = dict(_DATA, shape="ellipse")
        producers = [e for e in self._elements if name in e.produces]
        consumed = any(name in e.consumes for e in self._elements)
        if len(producers) != 1 or not consumed:
            attributes.update(color=_VERMILLION, penwidth="2")
        elif self._ran and not any(name in e.produced for e in producers):
            attributes.update(style="dashed", color=_GREY)
        return attributes

    def _unreachable(self, declared: str) -> bool:
        return any(
            not artifact.reachable
            and (artifact.path == declared or fnmatch.fnmatch(artifact.path, declared))
            for element in self._elements
            if declared in element.observes
            for artifact in element.artifacts
        )


def _overlay(style: dict[str, str], reported: ElementReport) -> dict[str, str]:
    """The attributes that draw ``reported``'s status over its kind's ``style``."""
    tooltip = str(reported.status) + (f": {reported.reason}" if reported.reason else "")
    if reported.status is Status.PASS:
        return {"color": _GREEN, "penwidth": "2", "tooltip": tooltip}
    filled = _styled(style, "filled")
    if reported.status is Status.FAIL:
        return {
            "style": filled,
            "fillcolor": _VERMILLION,
            "fontcolor": "white",
            "fontname": "Helvetica-Bold",
            "penwidth": "2",
            "tooltip": tooltip,
        }
    skipped = {"style": _styled(style, "filled", "dashed"), "fillcolor": _LIGHT_GREY}
    skipped.update(color=_GREY, tooltip=tooltip)
    if not reported.blocked_by:  # skipped on its own account: a root cause
        skipped["penwidth"] = "2"
    return skipped


def _styled(style: dict[str, str], *added: str) -> str:
    """The kind's DOT style, with ``added`` styles."""
    styles = [s for s in style.get("style", "").split(",") if s]
    return ",".join(styles + [s for s in added if s not in styles])


def _data_node(node: str, label: str, attributes: dict[str, str]) -> str:
    return f"{_INDENT}{_quoted(node)} [label={_quoted(label)}, {_attributes(attributes)}];"


def _data_edge(source: str, target: str, label: str, *, dotted: bool = False) -> str:
    if dotted:
        attributes = {"style": "dotted", "arrowhead": "empty"}
    else:
        attributes = {"style": "dashed", "color": _BLUE}
    attributes.update(label=f" {label}", fontsize="9")
    return f"{_INDENT}{_quoted(source)} -> {_quoted(target)} [{_attributes(attributes)}];"


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _attributes(attributes: dict[str, str]) -> str:
    return ", ".join(f"{key}={_value(value)}" for key, value in attributes.items())


def _value(value: str) -> str:
    """A DOT attribute value: bare when DOT allows it, as the compiler writes them, quoted
    otherwise."""
    return value if _BARE.fullmatch(value) else _quoted(value)


def _quoted(value: str) -> str:
    """``value`` in DOT double quotes, as the compiler quotes it (DotLabel.quoted)."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _wrapped(label: str) -> str:
    """``label`` wrapped at word boundaries and quoted, as the compiler wraps it
    (DotLabel.wrapAndQuote): no line longer than 40 characters once escaped, unless a word
    is, and ``_`` escaped."""
    lines: list[str] = []
    current = ""
    for word in label.split():
        escaped = word.replace("\\", "\\\\").replace('"', '\\"').replace("_", "\\_")
        if current and len(current) + 1 + len(escaped) > _WRAP_WIDTH:
            lines.append(current)
            current = escaped
        else:
            current = f"{current} {escaped}" if current else escaped
    if current:
        lines.append(current)
    return '"' + "\\n".join(lines) + '"'
