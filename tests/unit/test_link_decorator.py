import json
import os
import tempfile
import unittest

from jpipe_runner.framework.context import ctx
from jpipe_runner.framework.decorators.link_decorator import jpipe_link
from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.engine import PipelineEngine
from jpipe_runner.exceptions import RuntimeException
from jpipe_runner.runtime import PythonRuntime


class TestJpipeLinkDecorator(unittest.TestCase):
    def test_sets_link_id_on_plain_function(self):
        @jpipe_link("E1")
        def my_func():
            return True

        self.assertEqual(my_func.__jpipe_link_ids__, ["E1"])

    def test_stacked_decorators_accumulate_ids(self):
        # Two @jpipe_link decorators (aliases of the same node) must both be kept,
        # in bottom-to-top application order, rather than the last overwriting.
        @jpipe_link("rigor:r17:e_metric")
        @jpipe_link("rigor:r18:e")
        def my_func():
            return True

        self.assertEqual(
            my_func.__jpipe_link_ids__, ["rigor:r18:e", "rigor:r17:e_metric"]
        )

    def test_returns_original_function_unchanged(self):
        def my_func():
            return 42

        decorated = jpipe_link("E1")(my_func)
        self.assertIs(decorated, my_func)
        self.assertEqual(decorated(), 42)

    def test_link_id_propagates_through_jpipe_inner(self):
        ctx_backup = ctx._vars.copy()
        ctx._vars.clear()
        try:
            @jpipe(consume=[], produce=[])
            @jpipe_link("E1")
            def my_func():
                return True

            self.assertEqual(my_func.__jpipe_link_ids__, ["E1"])
        finally:
            ctx._vars = ctx_backup

    def test_link_id_propagates_through_jpipe_outer(self):
        ctx_backup = ctx._vars.copy()
        ctx._vars.clear()
        try:
            @jpipe_link("E1")
            @jpipe(consume=[], produce=[])
            def my_func():
                return True

            self.assertEqual(my_func.__jpipe_link_ids__, ["E1"])
        finally:
            ctx._vars = ctx_backup

    def test_stacked_alias_ids_survive_jpipe_wrapping(self):
        # The accumulated list must remain visible after @jpipe wraps the function,
        # because @jpipe uses @wraps which shares __dict__ references.
        ctx_backup = ctx._vars.copy()
        ctx._vars.clear()
        try:
            @jpipe_link("rigor:r17:e_metric")
            @jpipe_link("rigor:r18:e")
            @jpipe(consume=[], produce=[])
            def my_func():
                return True

            self.assertEqual(
                my_func.__jpipe_link_ids__, ["rigor:r18:e", "rigor:r17:e_metric"]
            )
        finally:
            ctx._vars = ctx_backup

    def test_function_name_preserved_after_decoration(self):
        ctx_backup = ctx._vars.copy()
        ctx._vars.clear()
        try:
            @jpipe_link("E1")
            @jpipe(consume=[], produce=[])
            def my_function():
                return True

            self.assertEqual(my_function.__name__, "my_function")
        finally:
            ctx._vars = ctx_backup


class TestBuildLinkRegistry(unittest.TestCase):
    def _write_module(self, tmp_dir, filename, code):
        path = os.path.join(tmp_dir, filename)
        with open(path, "w") as f:
            f.write(code)
        return path

    def test_returns_empty_dict_when_no_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_module(tmp, "no_links.py", "def plain(): return True\n")
            runtime = PythonRuntime(libraries=[path])
            self.assertEqual(runtime.build_link_registry(), {})

    def test_returns_correct_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = (
                "from jpipe_runner.framework.decorators.link_decorator import jpipe_link\n"
                "@jpipe_link('E1')\n"
                "def evidence_one(): return True\n"
            )
            path = self._write_module(tmp, "linked.py", code)
            runtime = PythonRuntime(libraries=[path])
            registry = runtime.build_link_registry()
            self.assertEqual(registry, {"E1": "evidence_one"})

    def test_multiple_linked_functions(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = (
                "from jpipe_runner.framework.decorators.link_decorator import jpipe_link\n"
                "@jpipe_link('E1')\n"
                "def func_a(): return True\n"
                "@jpipe_link('S2')\n"
                "def func_b(): return True\n"
            )
            path = self._write_module(tmp, "multi.py", code)
            runtime = PythonRuntime(libraries=[path])
            registry = runtime.build_link_registry()
            self.assertEqual(registry, {"E1": "func_a", "S2": "func_b"})

    def test_stacked_aliases_emit_every_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = (
                "from jpipe_runner.framework.decorators.link_decorator import jpipe_link\n"
                "@jpipe_link('rigor:r17:e_metric')\n"
                "@jpipe_link('rigor:r18:e')\n"
                "def unified(): return True\n"
            )
            path = self._write_module(tmp, "aliased.py", code)
            runtime = PythonRuntime(libraries=[path])
            registry = runtime.build_link_registry()
            self.assertEqual(
                registry,
                {"rigor:r17:e_metric": "unified", "rigor:r18:e": "unified"},
            )

    def test_same_name_on_two_functions_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = (
                "from jpipe_runner.framework.decorators.link_decorator import jpipe_link\n"
                "@jpipe_link('E1')\n"
                "def func_a(): return True\n"
                "@jpipe_link('E1')\n"
                "def func_b(): return True\n"
            )
            path = self._write_module(tmp, "dup.py", code)
            runtime = PythonRuntime(libraries=[path])
            with self.assertRaises(RuntimeException):
                runtime.build_link_registry()


class TestApplyLinkRegistry(unittest.TestCase):
    def _make_engine(self, tmp_path):
        data = {
            "name": "test",
            "type": "justification",
            "elements": [
                {"id": "E1", "type": "evidence", "label": "Some Label That Wont Match"},
                {"id": "C1", "type": "conclusion", "label": "Done"},
            ],
            "relations": [{"source": "E1", "target": "C1"}],
        }
        path = os.path.join(tmp_path, "j.json")
        with open(path, "w") as f:
            json.dump(data, f)
        from unittest.mock import patch
        with patch("jpipe_runner.framework.engine.PipelineEngine.load_config"):
            engine = PipelineEngine(None, path)
        return engine

    def test_updates_function_name_for_linked_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            engine._apply_link_registry({"E1": "my_custom_function"})
            self.assertEqual(engine.graph.nodes["E1"]["function_name"], "my_custom_function")

    def test_unlinked_node_keeps_sanitized_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            engine._apply_link_registry({"E1": "my_custom_function"})
            # C1 is not in the registry — its function_name should still be the sanitized label
            self.assertEqual(engine.graph.nodes["C1"]["function_name"], "done")

    def test_unknown_node_id_in_registry_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            # Should not raise even for ids not in the graph
            engine._apply_link_registry({"NONEXISTENT": "some_func"})
            self.assertNotIn("NONEXISTENT", engine.graph.nodes)

    def test_qualified_id_format_resolves_correctly(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            # "test:E1" should resolve to node "E1" when justification name is "test"
            engine._apply_link_registry({"test:E1": "my_custom_function"})
            self.assertEqual(engine.graph.nodes["E1"]["function_name"], "my_custom_function")

    def test_qualified_id_wrong_justification_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            original = engine.graph.nodes["E1"]["function_name"]
            # Wrong justification name — should not update the node
            engine._apply_link_registry({"other_pipeline:E1": "my_custom_function"})
            self.assertEqual(engine.graph.nodes["E1"]["function_name"], original)

    def test_resolve_node_id_plain(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            self.assertEqual(engine._resolve_node_id("E1"), "E1")

    def test_resolve_node_id_qualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            self.assertEqual(engine._resolve_node_id("test:E1"), "E1")

    def test_resolve_node_id_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            self.assertIsNone(engine._resolve_node_id("MISSING"))
            self.assertIsNone(engine._resolve_node_id("test:MISSING"))
            self.assertIsNone(engine._resolve_node_id("other:E1"))


class TestAliasResolution(unittest.TestCase):
    def _make_engine(self, tmp_path):
        data = {
            "name": "rigor",
            "type": "justification",
            "elements": [
                {
                    "id": "rigor:unified_0",
                    "type": "evidence",
                    "label": "The model reports its metrics",
                    "aliases": ["rigor:r17:e_metric", "rigor:r18:e"],
                },
                {"id": "C1", "type": "conclusion", "label": "Done"},
            ],
            "relations": [{"source": "rigor:unified_0", "target": "C1"}],
        }
        path = os.path.join(tmp_path, "j.json")
        with open(path, "w") as f:
            json.dump(data, f)
        from unittest.mock import patch
        with patch("jpipe_runner.framework.engine.PipelineEngine.load_config"):
            engine = PipelineEngine(None, path)
        return engine

    def test_alias_index_built_for_id_and_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            self.assertEqual(engine._alias_index["rigor:unified_0"], "rigor:unified_0")
            self.assertEqual(engine._alias_index["rigor:r17:e_metric"], "rigor:unified_0")
            self.assertEqual(engine._alias_index["rigor:r18:e"], "rigor:unified_0")

    def test_resolve_canonical_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            self.assertEqual(
                engine._resolve_node_id("rigor:unified_0"), "rigor:unified_0"
            )

    def test_resolve_colon_bearing_alias(self):
        # An alias containing colons must match exactly (not be rsplit into a bogus
        # qualifier/element pair) and resolve to the canonical id.
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            self.assertEqual(
                engine._resolve_node_id("rigor:r17:e_metric"), "rigor:unified_0"
            )
            self.assertEqual(
                engine._resolve_node_id("rigor:r18:e"), "rigor:unified_0"
            )

    def test_apply_registry_binds_via_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            engine._apply_link_registry({"rigor:r17:e_metric": "report_metrics"})
            self.assertEqual(
                engine.graph.nodes["rigor:unified_0"]["function_name"],
                "report_metrics",
            )

    def test_bound_node_ids_includes_alias_only_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            engine._apply_link_registry({"rigor:r18:e": "report_metrics"})
            self.assertIn("rigor:unified_0", engine._bound_node_ids())

    def test_bound_node_ids_two_aliases_same_function_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            engine._apply_link_registry(
                {"rigor:r17:e_metric": "report_metrics", "rigor:r18:e": "report_metrics"}
            )
            self.assertEqual(engine._bound_node_ids(), {"rigor:unified_0"})

    def test_bound_node_ids_conflicting_functions_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._make_engine(tmp)
            # Two different aliases of the SAME node bound to DIFFERENT functions.
            engine._link_registry = {
                "rigor:r17:e_metric": "func_a",
                "rigor:r18:e": "func_b",
            }
            with self.assertRaises(RuntimeException):
                engine._bound_node_ids()


if __name__ == "__main__":
    unittest.main()
