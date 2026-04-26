"""
jpipe_runner.framework.graphviz_exporter
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Graphviz rendering for justification pipeline graphs.
"""

from pathlib import Path
from typing import Any

import networkx as nx

from ..enums import StatusType
from .logger import GLOBAL_LOGGER


class GraphvizExporter:
    """
    Renders a justification pipeline graph to an image file via Graphviz.

    Handles DOT-safe node ID sanitization: element IDs containing `:`
    (e.g. ``final:hook``) are replaced with ``_`` in the DOT graph while
    the human-readable label is preserved for display.
    """

    _NODE_STYLES: dict[str, dict[str, str]] = {
        "conclusion":     {"shape": "rect",    "style": "filled,rounded", "fillcolor": "lightgrey"},
        "sub-conclusion": {"shape": "rect",    "color": "#0072B2"},
        "strategy":       {"shape": "hexagon", "style": "filled",         "fillcolor": "#F0C27F"},
        "evidence":       {"shape": "note",    "style": "filled",         "fillcolor": "#9ECAE1"},
        "support":        {"shape": "rect",    "style": "dotted"},
    }

    def __init__(self, graph: nx.DiGraph) -> None:
        self.graph = graph

    def export(
        self, status_dict: dict[str, str], output_path: str, filename: str, fmt: str
    ) -> None:
        """
        Render the pipeline graph to an image file.

        :param status_dict: Mapping of node id → status string ("PASS", "FAIL", "SKIP").
        :param output_path: Directory path to save the exported image.
        :param filename: Output filename (without extension).
        :param fmt: Image format string (e.g. "png", "svg", "dot").
        """
        import graphviz as gv

        resolved_path = self._resolve_output_path(output_path, filename)
        dot = gv.Digraph()
        dot.attr(rankdir="BT")
        self._style_nodes(dot, status_dict)
        self._style_edges(dot, status_dict)
        dot.render(
            str(resolved_path),
            format=fmt,
            engine="dot",
            cleanup=True,
            outfile=str(resolved_path.with_suffix(f".{fmt}")),
        )

    @staticmethod
    def _dot_id(node_id: str) -> str:
        """Return a DOT-safe identifier by replacing `:` with `_`."""
        return node_id.replace(":", "_")

    def _style_nodes(self, dot: Any, status_dict: dict[str, str]) -> None:
        """Add nodes to *dot* styled by element type and execution status."""
        for node_id, attrs in self.graph.nodes(data=True):
            var_type = attrs.get("type", "").lower()
            style = dict(self._NODE_STYLES.get(
                var_type, {"fillcolor": "white", "shape": "ellipse", "style": "filled"}
            ))

            status = status_dict.get(node_id, "UNKNOWN")
            GLOBAL_LOGGER.info("Setting node color for %s with status %s", node_id, status)
            if status == StatusType.FAIL.name:
                style.update(style="filled", fillcolor="red", fontcolor="white", fontname="Helvetica-Bold")
            elif status == StatusType.SKIP.name:
                style.update(style="filled", fillcolor="#cccccc", opacity="1", fontcolor="white", fontname="Helvetica-Bold")

            label = attrs.get("label", node_id)
            dot.node(self._dot_id(node_id), label=label, **style)

    def _style_edges(self, dot: Any, status_dict: dict[str, str]) -> None:
        """Add edges to *dot* colored by the source node's execution status."""
        for source, target in self.graph.edges():
            status = status_dict.get(source, "UNKNOWN")
            GLOBAL_LOGGER.info("Setting edge color for %s -> %s with status %s", source, target, status)
            if status == StatusType.PASS.name:
                dot.edge(self._dot_id(source), self._dot_id(target), color="black")
            elif status == StatusType.FAIL.name:
                dot.edge(self._dot_id(source), self._dot_id(target), color="red")
            elif status == StatusType.SKIP.name:
                dot.edge(self._dot_id(source), self._dot_id(target), color="#cccccc", opacity="1")
            else:
                dot.edge(self._dot_id(source), self._dot_id(target), color="gray")

    @staticmethod
    def _resolve_output_path(output_path: str, filename: str) -> Path:
        """Resolve and prepare the output directory, returning the full file path."""
        path = Path(output_path)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        return path / filename
