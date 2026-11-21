"""The diagram of a run: the dataflow of a justification, with what the run concluded
(ADR-0029).

``source(justification, report)`` is the Graphviz DOT text of the diagram, and ``write``
renders it to a file. It draws the argument in the jPipe compiler's notation (its shapes and
colours, from the Okabe-Ito palette, and its labels wrapped at 40 characters), and adds what
the steps declare: each file or glob an evidence observes, and each value a step produces
or consumes, as nodes linked to the elements. A value is a variable and the step that
produces it: two steps that produce one variable are two nodes, and each consumer is
linked to the one it receives (ADR-0031). A value nothing consumes, a consumed variable
that resolves to no single producer, and a file that could not be reached, are drawn in
vermillion.

A support edge is left out when a variable already links its two ends: when the supporter
produces a variable the element it supports consumes, the path through that variable shows
the support, and the data that flows along it.

A justification that implements templates is drawn as the compiler draws it, from the
template chain jPipe 4.0.0 writes to its JSON: each template a cluster labelled
``<<template>> name``, nested in the one before it; each ``@support`` a dotted placeholder,
``<id>@abstract``, linked by a dotted arrow from the element that fills it; and the
template's supports drawn from the placeholder. No variable links a placeholder, so those
are drawn even when one links the element that fills it to the strategy: they are the
template's structure. A placeholder has no step, so no status.

A run's statuses are drawn over the elements, in the same palette, and each as a symbol
beside the label, so that the diagram reads without its colours:

- **pass**: ✔, the element with a green border;
- **fail**: ✘, filled vermillion, in white text;
- **skip**: ◌, filled light grey, with a dashed grey border, thicker when it is a root cause.

The symbol is drawn in the label's colour, which contrasts with every fill. A status never
moves the diagram (#186): drawn with a report, every node's label is an HTML-like label,
wrapped as the compiler wraps it, beside a cell of fixed size for its symbol, empty when
it has none, and a status changes no font. A dry run's diagram, and the diagrams of two
runs with different statuses, therefore put every node in the same place. A file or
variable drawn in vermillion is marked ⚠, in a cell of its own. A support edge takes the
colour of the status of the element it comes from, or, from a placeholder, of the element
that fills it, and is thicker from a failure, dashed from a skip. In SVG, a node's tooltip
gives its status and reason. Without a report, the diagram is the argument alone; with the
report of a run in which nothing ran, such as a dry run, it is the dataflow the steps
declare, without statuses.

Rendering pipes the DOT text to Graphviz's ``dot``: only the binary is needed. The ``dot``
format is the text itself, written without it.
"""

import html
import os
import re
import secrets
import shutil
import subprocess
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

from jpipe_runner.dataflow import Received
from jpipe_runner.engine import Status
from jpipe_runner.model import Element, Justification, Kind, Template
from jpipe_runner.observables import DEFAULT_SHAPE, Observation
from jpipe_runner.report import ElementReport, RunReport

FORMATS = ("dot", "gif", "jpeg", "jpg", "pdf", "png", "svg")

_WINDOWS = os.name == "nt"
_ATTEMPTS, _PAUSE = 10, 0.1
"""How many times, and how far apart in seconds, a diagram is renamed into place."""

_WRAP_WIDTH = 40

# The compiler's notation (DotNodeStyle, jPipe 2.5.0): shape, style, fill, border.
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
_SYMBOLS = {Status.PASS: "✔", Status.FAIL: "✘", Status.SKIP: "◌"}
_WARNING = "⚠"
_OBSERVED = "✔"

# The cell a symbol is drawn in: its point size, then the cell's fixed width and height, in
# points, wider and taller than any of its symbols, so that every node keeps its size
# whatever the cell holds (#186).
_Cell = tuple[str, str, str]
_STATUS_CELL: _Cell = ("20", "28", "32")
_DATA_CELL: _Cell = ("14", "22", "22")
_DATA = {"fontname": "Courier", "fontsize": "10"}
_PROBLEM = {"color": _VERMILLION, "penwidth": "2"}

# A template's @support, in the compiler's notation: a dotted box, named after the element
# that fills it.
_PLACEHOLDER = {"shape": "rect", "style": "dotted"}

_BARE = re.compile(r"[A-Za-z_]\w*|\d+", re.ASCII)
"""What DOT accepts unquoted, of the values a diagram uses: a name, or a whole number."""
_INDENT = "  "


def source(justification: Justification, report: RunReport | None = None) -> str:
    """The DOT text of the diagram of ``justification``, with what ``report`` concluded.

    The diagram is drawn from the model, in the order of its elements and relations, and
    from what ``report`` says the steps declare, so ``report`` must be a report of that
    model: raises ``ValueError`` if its elements, or what each supports, differ from the
    model's.
    """
    if report is not None:
        _check_reports_on(report, justification)
    reported = {} if report is None else {e.id: e for e in report.elements}
    drawn = _Diagram(justification, reported, overlaid=report is not None)
    return "".join(f"{line}\n" for line in drawn.lines())


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
    fmt: str | None = None,
) -> Path:
    """Write the diagram to ``path``, in ``fmt``, by default its suffix, and return ``path``.

    The directory is created if it does not exist. The diagram is drawn in a temporary
    file beside ``path``, then renamed to it, so that a program that reads ``path`` while
    it is written, such as one that follows a run (ADR-0032), sees the previous drawing
    or the new one, never half of one; a diagram that cannot be drawn leaves ``path`` as
    it was. The file has the permissions of the one it replaces, or those a new file gets,
    and a link at ``path`` is written through, to the file it links to. Raises
    ``ValueError`` for a format not in ``FORMATS``, ``FileNotFoundError`` if Graphviz's
    ``dot`` is not installed, and ``OSError`` if it fails.
    """
    fmt = (fmt or path.suffix.removeprefix(".")).lower()
    if fmt not in FORMATS:
        raise ValueError(f"a diagram is one of {', '.join(FORMATS)}, not {fmt!r}")
    text = source(justification, report)
    target = path.resolve() if path.is_symlink() else path
    target.parent.mkdir(parents=True, exist_ok=True)
    drawing = _temporary(target)
    try:
        # Before anything is written, so that a private diagram is never readable by others.
        if target.exists():
            shutil.copymode(target, drawing)
        _draw(text, fmt, drawing, path)
        _replace(drawing, target)
    finally:
        drawing.unlink(missing_ok=True)
    return path


def _temporary(target: Path) -> Path:
    """A new, empty file beside ``target``, with the permissions a new file gets."""
    while True:
        drawing = target.with_name(f".{target.name}.{secrets.token_hex(4)}.tmp")
        try:
            os.close(os.open(drawing, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666))
        except FileExistsError:  # pragma: no cover - 32 random bits, taken already
            continue
        return drawing


def _replace(drawing: Path, target: Path) -> None:
    """Rename ``drawing`` to ``target``. On Windows, a file another program has open cannot
    be replaced, as the reader of a run's diagram may have it for a moment: try again,
    for about a second."""
    for attempt in range(_ATTEMPTS):
        try:
            os.replace(drawing, target)
            return
        except PermissionError:
            if not _WINDOWS or attempt == _ATTEMPTS - 1:
                raise
            time.sleep(_PAUSE)


def _draw(text: str, fmt: str, drawing: Path, path: Path) -> None:
    """Write ``text`` to ``drawing``, rendered in ``fmt``: the drawing of ``path``."""
    if fmt == "dot":
        drawing.write_text(text, encoding="utf-8")
        return
    try:
        rendered = subprocess.run(
            ["dot", f"-T{fmt}", "-o", str(drawing)],
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


class _Diagram:
    """The DOT lines of one diagram."""

    def __init__(
        self, model: Justification, reported: dict[str, ElementReport], *, overlaid: bool
    ) -> None:
        self._model = model
        self._reported = reported
        self._overlaid = overlaid
        self._dataflow = _Dataflow(reported)
        self._chain = model.template_chain
        templates = () if self._chain is None else self._chain.templates
        self._placeholders = [p for template in templates for p in template.placeholders]
        self._from_placeholder = {
            (placeholder.id, strategy)
            for placeholder in self._placeholders
            for strategy in placeholder.supports
        }

    def lines(self) -> Iterator[str]:
        yield f"digraph {_quoted(self._model.name)} {{"
        yield f"{_INDENT}rankdir=BT;"
        yield f"{_INDENT}label={_wrapped(self._model.name)};"
        yield from self._nodes()
        yield from self._dataflow.nodes()
        for placeholder in self._placeholders:
            override = f"{_quoted(placeholder.id)} -> {_quoted(_abstract(placeholder.id))}"
            yield f"{_INDENT}{override} [arrowhead=empty, style=dotted];"
        for relation in self._model.relations:
            if (relation.source, relation.target) in self._from_placeholder:
                yield self._edge(relation.source, relation.target, _abstract(relation.source))
            elif not self._dataflow.links(relation.source, relation.target):
                yield self._edge(relation.source, relation.target)
        yield from self._dataflow.edges()
        yield "}"

    def _nodes(self) -> Iterator[str]:
        """The elements, and the templates they are drawn in, if the model implements any."""
        if self._chain is None:
            for element in self._model:
                yield self._node(element, _INDENT)
            return
        placed = set(self._chain.elements)
        for template in self._chain.templates:
            abstract = {placeholder.id for placeholder in template.placeholders}
            placed.update(i for i in template.elements if i not in abstract)
        for element_id in self._chain.elements:
            yield self._node(self._model.element(element_id), _INDENT)
        for element in self._model:  # none, from the compiler: drawn rather than lost
            if element.id not in placed:
                yield self._node(element, _INDENT)
        yield from self._templates(self._chain.templates, _INDENT)

    def _templates(self, templates: tuple[Template, ...], indent: str) -> Iterator[str]:
        """The first of ``templates`` as a cluster, with the others nested inside it."""
        if not templates:
            return
        template, inner = templates[0], templates[1:]
        inside = indent + _INDENT
        placeholders = {placeholder.id: placeholder for placeholder in template.placeholders}
        yield f"{indent}subgraph {_quoted(f'cluster_{template.name}')} {{"
        yield f"{inside}style=filled; fillcolor=lightyellow; color=grey;"
        yield f"{inside}label={_wrapped(f'<<template>> {template.name}')};"
        for element_id in template.elements:
            if (placeholder := placeholders.get(element_id)) is not None:
                drawn = _quoted(_abstract(element_id))
                head = f"label={_wrapped(placeholder.label)}, id={drawn}"
                yield f"{inside}{drawn} [{head}, {_attributes(_PLACEHOLDER)}];"
            else:
                yield self._node(self._model.element(element_id), inside)
        yield from self._templates(inner, inside)
        yield f"{indent}}}"

    def _node(self, element: Element, indent: str) -> str:
        """An element, in its kind's style. Drawn with a report, its label has a cell for
        its status, empty when it has none, so that a status changes its colours and
        symbol, never its size: a run's diagrams line up whatever their statuses (#186)."""
        reported = self._reported.get(element.id)
        attributes = dict(_KIND_STYLES[element.kind])
        label = _wrapped(element.label)
        if self._overlaid:
            status = None if reported is None else reported.status
            if reported is not None and status is not None:
                attributes.update(_overlay(attributes, reported))
            lines = [" ".join(line) for line in _wrap(element.label)]
            label = _marked(lines, None if status is None else _SYMBOLS[status], _STATUS_CELL)
        head = f"label={label}, id={_quoted(element.id)}"
        return f"{indent}{_quoted(element.id)} [{head}, {_attributes(attributes)}];"

    def _edge(self, source: str, target: str, drawn_from: str | None = None) -> str:
        """The support of ``target`` by ``source``, drawn from ``drawn_from`` if given, in
        the colour of ``source``'s status."""
        reported = self._reported.get(source)
        status = None if reported is None else reported.status
        edge = f"{_INDENT}{_quoted(drawn_from or source)} -> {_quoted(target)}"
        if status is None:
            return f"{edge};"
        attributes = {"color": _EDGE_COLOURS[status]}
        if status is Status.FAIL:
            attributes["penwidth"] = "2"
        elif status is Status.SKIP:
            attributes["style"] = "dashed"
        return f"{edge} [{_attributes(attributes)}];"


class _Dataflow:
    """The files and values a run's steps declare, as nodes and edges.

    A value's node is named after its variable, ``variable coverage``, and after its
    producer too, ``variable coverage from m:e``, when several steps produce the variable.
    A consumed variable that resolves to no single producer has a node of its own, named
    after the variable, unless one step produces it: then it is drawn from that one, which
    validation reports does not support the consumer (JP014). Either way, the value is
    drawn in vermillion.
    """

    def __init__(self, reported: dict[str, ElementReport]) -> None:
        self._reported = reported
        self._elements = list(reported.values())
        self._ran = any(element.status is not None for element in self._elements)
        self._producers: dict[str, list[str]] = {}
        for element in self._elements:
            for name in element.produces:
                self._producers.setdefault(name, []).append(element.id)
        self._produced_by: dict[str, str] = {}
        self._consumers: dict[str, set[str]] = {}
        self._unresolved: set[str] = set()
        for element in self._elements:
            for name in element.produces:
                self._produced_by[self._node(name, element.id)] = element.id
            for received in self._inputs(element):
                node = self._source(received)
                self._consumers.setdefault(node, set()).add(element.id)
                if received.produced_by is None:
                    self._unresolved.add(node)
        self._links = {
            (self._produced_by[node], consumer)
            for node, consumers in self._consumers.items()
            if node in self._produced_by
            for consumer in consumers
        }

    def links(self, source: str, target: str) -> bool:
        """Whether a value links ``source`` to ``target``: ``source`` produces it and
        ``target`` consumes it."""
        return (source, target) in self._links

    def nodes(self) -> Iterator[str]:
        for path in _unique(p for e in self._elements for p in e.sources):
            yield self._source_node(path)
        for node, name in self._values():
            yield _variable_node(node, name, self._variable(node, name), self._broken(node))

    def _source_node(self, declared: str) -> str:
        """What an evidence observes, in the shape its observable says. Its label has a
        cell for a symbol: ✔ once it was observed, ⚠ when it could not be, empty while it
        was not, as in a dry run. A source that could not be observed is drawn in
        vermillion too."""
        attributes = dict(_DATA, shape=self._shape(declared))
        seen = self._seen(declared)
        unreachable = any(not observation.reachable for observation in seen)
        if unreachable:
            attributes |= _PROBLEM
        symbol = _WARNING if unreachable else _OBSERVED if seen else None
        drawn = _marked([declared], symbol, _DATA_CELL)
        node = _quoted(f"artifact {declared}")
        return f"{_INDENT}{node} [label={drawn}, {_attributes(attributes)}];"

    def _shape(self, declared: str) -> str:
        """The shape of the first element's observable that ``declared`` names."""
        for element in self._elements:
            if (shape := element.shapes.get(declared)) is not None:
                return shape
        return DEFAULT_SHAPE

    def _seen(self, declared: str) -> list[Observation]:
        """What the run observed of ``declared``, for every element that observes it."""
        return [
            observation
            for element in self._elements
            for observation in element.artifacts
            if observation.declared == declared
        ]

    def edges(self) -> Iterator[str]:
        for element in self._elements:
            for path in element.sources:
                yield _data_edge(f"artifact {path}", element.id, "observes", dotted=True)
            for name in element.produces:
                yield _data_edge(element.id, self._node(name, element.id), "produces")
            for node in _unique(self._source(received) for received in self._inputs(element)):
                yield _data_edge(node, element.id, "consumes")

    def _node(self, name: str, producer: str | None) -> str:
        """The node of ``name`` as ``producer`` produces it, or of ``name`` unresolved."""
        if producer is None or len(self._producers.get(name, ())) <= 1:
            return f"variable {name}"
        return f"variable {name} from {producer}"

    def _source(self, received: Received) -> str:
        """The node a parameter receives its value from."""
        producer = received.produced_by or self._only(received.variable)
        return self._node(received.variable, producer)

    def _values(self) -> list[tuple[str, str]]:
        """Each value's node and its variable, in the order the elements declare them."""
        found: dict[str, str] = {}
        for element in self._elements:
            for name in element.produces:
                found.setdefault(self._node(name, element.id), name)
            for received in self._inputs(element):
                found.setdefault(self._source(received), received.variable)
        return list(found.items())

    def _variable(self, node: str, name: str) -> dict[str, str]:
        """The style of a value: dashed and grey when it was not produced."""
        attributes = dict(_DATA, shape="ellipse")
        producer = self._produced_by.get(node)
        produced = producer is not None and name in self._reported[producer].produced
        if self._ran and not produced and not self._broken(node):
            attributes.update(style="dashed", color=_GREY)
        return attributes

    def _broken(self, node: str) -> bool:
        """Whether a value lacks a producer, or a consumer, or is consumed by a step that
        does not resolve to it."""
        return (
            node not in self._produced_by or node not in self._consumers or node in self._unresolved
        )

    def _inputs(self, element: ElementReport) -> tuple[Received, ...]:
        """What ``element``'s step receives: its inputs, or, in a report that has none, each
        variable it consumes, to a parameter of the same name, from its producer if only one
        step produces it."""
        if element.inputs or not element.consumes:
            return element.inputs
        return tuple(Received(name, name, self._only(name)) for name in element.consumes)

    def _only(self, name: str) -> str | None:
        """The one element that produces ``name``, if only one does."""
        producers = self._producers.get(name, [])
        return producers[0] if len(producers) == 1 else None


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


def _variable_node(node: str, label: str, attributes: dict[str, str], problem: bool) -> str:
    """A variable, in vermillion when it is a ``problem``. It has no symbol: whether it is
    one is known before the run, from the declarations, so a run never moves it."""
    if problem:
        attributes = attributes | _PROBLEM
    return f"{_INDENT}{_quoted(node)} [label={_quoted(label)}, {_attributes(attributes)}];"


def _data_edge(source: str, target: str, label: str, *, dotted: bool = False) -> str:
    if dotted:
        attributes = {"style": "dotted", "arrowhead": "empty"}
    else:
        attributes = {"style": "dashed", "color": _BLUE}
    attributes.update(label=f" {label}", fontsize="9")
    return f"{_INDENT}{_quoted(source)} -> {_quoted(target)} [{_attributes(attributes)}];"


def _abstract(element_id: str) -> str:
    """The node of the placeholder ``element_id`` fills, named as the compiler names it."""
    return f"{element_id}@abstract"


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
    return '"' + _escaped(value) + '"'


def _escaped(value: str) -> str:
    """``value`` with its backslashes and double quotes escaped, for DOT double quotes."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _wrapped(label: str) -> str:
    """``label`` wrapped and quoted, as the compiler wraps it (DotLabel.wrapAndQuote), with
    ``_`` escaped."""
    lines = (" ".join(_dot_word(word) for word in line) for line in _wrap(label))
    return '"' + "\\n".join(lines) + '"'


def _wrap(label: str) -> list[list[str]]:
    """The words of ``label``, line by line, wrapped at word boundaries as the compiler wraps
    them: no line longer than 40 characters once escaped for DOT, unless a word is."""
    lines: list[list[str]] = []
    current: list[str] = []
    width = 0
    for word in label.split():
        size = len(_dot_word(word))
        if current and width + 1 + size > _WRAP_WIDTH:
            lines.append(current)
            current, width = [], 0
        width += size + (1 if current else 0)
        current.append(word)
    if current:
        lines.append(current)
    return lines


def _dot_word(word: str) -> str:
    """``word`` escaped as the compiler escapes a label's word."""
    return _escaped(word).replace("_", "\\_")


def _marked(lines: list[str], symbol: str | None, cell: _Cell) -> str:
    """An HTML-like label: ``lines``, beside a ``cell`` of fixed size that holds
    ``symbol``, or nothing."""
    size, width, height = cell
    text = "<br/>".join(_html(line) for line in lines)
    table = '<table border="0" cellborder="0" cellspacing="0">'
    held = "" if symbol is None else f'<font point-size="{size}">{symbol}</font>'
    symbol_cell = f'<td fixedsize="true" width="{width}" height="{height}">{held}</td>'
    return f"<{table}<tr>{symbol_cell}<td>{text}</td></tr></table>>"


def _html(text: str) -> str:
    """``text`` escaped for an HTML-like label: its markup, and its backslashes, which
    Graphviz would read as escapes such as ``\\N`` (the node's id) even in HTML text."""
    return html.escape(text.replace("\\", "\\\\"))
