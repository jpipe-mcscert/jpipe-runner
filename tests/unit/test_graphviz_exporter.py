import unittest
from unittest.mock import MagicMock, call, patch

import networkx as nx

from jpipe_runner.framework.graphviz_exporter import GraphvizExporter


def _make_graph(nodes: list[tuple[str, dict]], edges: list[tuple[str, str]]) -> nx.DiGraph:
    G = nx.DiGraph()
    for node_id, attrs in nodes:
        G.add_node(node_id, **attrs)
    G.add_edges_from(edges)
    return G


class TestDotId(unittest.TestCase):
    def test_replaces_colons(self):
        self.assertEqual(GraphvizExporter._dot_id("final:hook:e1"), "final_hook_e1")

    def test_no_colons_unchanged(self):
        self.assertEqual(GraphvizExporter._dot_id("E1"), "E1")

    def test_single_colon(self):
        self.assertEqual(GraphvizExporter._dot_id("a:b"), "a_b")


class TestStyleNodes(unittest.TestCase):
    def setUp(self):
        self.graph = _make_graph(
            [
                ("final:hook", {"type": "sub-conclusion", "label": "The model converges"}),
                ("final:e1",   {"type": "evidence",       "label": "Data available"}),
            ],
            [],
        )
        self.exporter = GraphvizExporter(self.graph)

    def test_sanitized_id_used_for_dot_node(self):
        dot = MagicMock()
        self.exporter._style_nodes(dot, {})
        called_ids = [c.args[0] for c in dot.node.call_args_list]
        self.assertIn("final_hook", called_ids)
        self.assertIn("final_e1", called_ids)

    def test_original_label_preserved(self):
        dot = MagicMock()
        self.exporter._style_nodes(dot, {})
        labels = {c.args[0]: c.kwargs.get("label") for c in dot.node.call_args_list}
        self.assertEqual(labels["final_hook"], "The model converges")
        self.assertEqual(labels["final_e1"], "Data available")

    def test_status_lookup_uses_original_id(self):
        dot = MagicMock()
        status_dict = {"final:hook": "FAIL"}
        self.exporter._style_nodes(dot, status_dict)
        kwargs_by_id = {c.args[0]: c.kwargs for c in dot.node.call_args_list}
        self.assertEqual(kwargs_by_id["final_hook"].get("fillcolor"), "red")


class TestStyleEdges(unittest.TestCase):
    def setUp(self):
        self.graph = _make_graph(
            [
                ("a:b", {"type": "evidence", "label": "A"}),
                ("c:d", {"type": "strategy", "label": "C"}),
            ],
            [("a:b", "c:d")],
        )
        self.exporter = GraphvizExporter(self.graph)

    def test_sanitized_ids_used_for_dot_edge(self):
        dot = MagicMock()
        self.exporter._style_edges(dot, {"a:b": "PASS"})
        dot.edge.assert_called_once_with("a_b", "c_d", color="black")

    def test_fail_edge_color(self):
        dot = MagicMock()
        self.exporter._style_edges(dot, {"a:b": "FAIL"})
        dot.edge.assert_called_once_with("a_b", "c_d", color="red")

    def test_skip_edge_color(self):
        dot = MagicMock()
        self.exporter._style_edges(dot, {"a:b": "SKIP"})
        dot.edge.assert_called_once_with("a_b", "c_d", color="#cccccc", opacity="1")

    def test_unknown_edge_color(self):
        dot = MagicMock()
        self.exporter._style_edges(dot, {})
        dot.edge.assert_called_once_with("a_b", "c_d", color="gray")


class TestExport(unittest.TestCase):
    def test_export_calls_render(self):
        graph = _make_graph([("n:1", {"type": "evidence", "label": "N"})], [])
        exporter = GraphvizExporter(graph)

        mock_dot = MagicMock()
        mock_digraph_cls = MagicMock(return_value=mock_dot)

        with patch.dict("sys.modules", {"graphviz": MagicMock(Digraph=mock_digraph_cls)}):
            import importlib
            import jpipe_runner.framework.graphviz_exporter as mod
            importlib.reload(mod)
            GraphvizExporter(graph).export({}, ".", "out", "svg")

        mock_dot.render.assert_called_once()


if __name__ == "__main__":
    unittest.main()
