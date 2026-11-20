"""The diagram of a run: the dataflow of a justification, with what the run concluded
(ADR-0029).

``source(justification, report)`` is the Graphviz DOT text of the diagram, and ``write``
renders it to a file. It draws the argument in the jPipe compiler's notation (its shapes and
colours, from the Okabe-Ito palette, and its labels wrapped at 40 characters), and adds what
the steps declare: each file or glob an evidence observes, and each variable a step produces
or consumes, as nodes linked to the elements. A variable without a producer or a consumer,
or with several producers, and a file that could not be reached, are drawn in vermillion.

A support edge is left out when a variable already links its two ends: when the supporter
produces a variable the element it supports consumes, the path through that variable shows
the support, and the data that flows along it.

A justification that implements templates is drawn as the compiler draws it, from the
template chain jPipe 4.0.0 writes to its JSON: each template a cluster labelled
``<<template>> name``, nested in the one before it; each ``@support`` a dotted placeholder,
``<id>@abstract``, linked by a dotted arrow from the element that fills it; and the
template's supports drawn from the placeholder. Those are drawn even when a variable links
their ends: they are the template's structure. A placeholder has no step, so no status.

A run's statuses are drawn over the elements, in the same palette:

- **pass**: the element, with a green border;
- **fail**: filled vermillion, in white bold text;
- **skip**: filled light grey, with a dashed grey border, thicker when it is a root cause.

A support edge takes the colour of the status of the element it comes from, or, from a
placeholder, of the element that fills it. In SVG, a
node's tooltip gives its status and reason. Without a report, or for a run in which nothing
ran, the diagram is the argument alone.

Rendering pipes the DOT text to Graphviz's ``dot``: only the binary is needed. The ``dot``
format is the text itself, written without it.
"""

import re
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path

from jpipe_runner.engine import Status
from jpipe_runner.model import Element, Justification, Kind, Template
from jpipe_runner.report import ElementReport, RunReport

FORMATS = ("dot", "gif", "jpeg", "jpg", "pdf", "png", "svg")

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
_DATA = {"fontname": "Courier", "fontsize": "10"}

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
    return "".join(f"{line}\n" for line in _Diagram(justification, reported).lines())


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

    The directory is created if it does not exist. Raises ``ValueError`` for a format not
    in ``FORMATS``, ``FileNotFoundError`` if Graphviz's ``dot`` is not installed, and
    ``OSError`` if it fails.
    """
    fmt = (fmt or path.suffix.removeprefix(".")).lower()
    if fmt not in FORMATS:
        raise ValueError(f"a diagram is one of {', '.join(FORMATS)}, not {fmt!r}")
    text = source(justification, report)
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

    def __init__(self, model: Justification, reported: dict[str, ElementReport]) -> None:
        self._model = model
        self._reported = reported
        self._dataflow = _Dataflow(reported)
        self._chain = model.template_chain
        templates = () if self._chain is None else self._chain.templates
        self._placeholders = [p for template in templates for p in template.placeholders]
        self._from_placeholder = {
            (placeholder.id, strategy): _abstract(placeholder.id)
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
            drawn_from = self._from_placeholder.get((relation.source, relation.target))
            if drawn_from is not None or not self._dataflow.links(relation.source, relation.target):
                yield self._edge(relation.source, relation.target, drawn_from)
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
        yield f"{inside}label={_quoted(f'<<template>> {template.name}')};"
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
        reported = self._reported.get(element.id)
        attributes = dict(_KIND_STYLES[element.kind])
        if reported is not None and reported.status is not None:
            attributes.update(_overlay(attributes, reported))
        head = f"label={_wrapped(element.label)}, id={_quoted(element.id)}"
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
        if status is Status.SKIP:
            attributes["style"] = "dashed"
        return f"{edge} [{_attributes(attributes)}];"


class _Dataflow:
    """The files and variables a run's steps declare, as nodes and edges."""

    def __init__(self, reported: dict[str, ElementReport]) -> None:
        self._reported = reported
        self._elements = list(reported.values())
        self._ran = any(element.status is not None for element in self._elements)

    def links(self, source: str, target: str) -> bool:
        """Whether a variable links ``source`` to ``target``: one ``source`` produces and
        ``target`` consumes."""
        produced, consumer = self._reported.get(source), self._reported.get(target)
        if produced is None or consumer is None:
            return False
        return not set(produced.produces).isdisjoint(consumer.consumes)

    def nodes(self) -> Iterator[str]:
        for path in _unique(p for e in self._elements for p in e.sources):
            attributes = dict(_DATA, shape="folder")
            if self._unreachable(path):
                attributes.update(color=_VERMILLION, penwidth="2")
            yield _data_node(f"artifact {path}", path, attributes)
        for name in self._variables():
            yield _data_node(f"variable {name}", name, self._variable(name))

    def edges(self) -> Iterator[str]:
        for element in self._elements:
            for path in element.sources:
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
            not observation.reachable and observation.declared == declared
            for element in self._elements
            for observation in element.artifacts
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
    """``label`` wrapped at word boundaries and quoted, as the compiler wraps it
    (DotLabel.wrapAndQuote): no line longer than 40 characters once escaped, unless a word
    is, and ``_`` escaped."""
    lines: list[str] = []
    current = ""
    for word in label.split():
        escaped = _escaped(word).replace("_", "\\_")
        if current and len(current) + 1 + len(escaped) > _WRAP_WIDTH:
            lines.append(current)
            current = escaped
        else:
            current = f"{current} {escaped}" if current else escaped
    if current:
        lines.append(current)
    return '"' + "\\n".join(lines) + '"'
