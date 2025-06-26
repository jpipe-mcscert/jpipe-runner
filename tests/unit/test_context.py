import unittest
from jpipe_runner.framework.context import RuntimeContext


class TestRuntimeContext(unittest.TestCase):
    def setUp(self):
        self.ctx = RuntimeContext()

    def test_set_and_get_produce_variable(self):
        self.ctx._set("func1", "var1", "value1", RuntimeContext.PRODUCE)
        result = self.ctx.get("var1")
        self.assertEqual(result, "value1")

    def test_set_and_get_consume_variable(self):
        self.ctx._set("func2", "var2", "value2", RuntimeContext.CONSUME)
        result = self.ctx.get("var2")
        self.assertEqual(result, "value2")

    def test_get_nonexistent_variable(self):
        result = self.ctx.get("nonexistent")
        self.assertIsNone(result)

    def test_set_existing_variable_value(self):
        self.ctx._set("func1", "var1", None, RuntimeContext.PRODUCE)
        self.ctx.set("var1", "new_value")
        result = self.ctx.get("var1")
        self.assertEqual(result, "new_value")

    def test_set_does_nothing_if_key_not_found(self):
        self.ctx.set("nonexistent_key", "value")
        # Nothing to assert directly, but no error should be raised
        self.assertIsNone(self.ctx.get("nonexistent_key"))

    def test_has_returns_true_when_key_exists(self):
        self.ctx._set("func1", "var1", "value1", RuntimeContext.CONSUME)
        self.assertTrue(self.ctx.has("func1", "var1"))

    def test_has_returns_false_when_key_does_not_exist(self):
        self.ctx._set("func1", "var1", "value1", RuntimeContext.PRODUCE)
        self.assertFalse(self.ctx.has("func1", "var2"))

    def test_has_returns_false_when_func_does_not_exist(self):
        self.assertFalse(self.ctx.has("unknown_func", "var1"))

    def test_set_from_config_sets_existing_key(self):
        self.ctx._set("func1", "var1", None, RuntimeContext.CONSUME)
        self.ctx.set_from_config("var1", "configured_value", decorator=RuntimeContext.CONSUME)
        result = self.ctx.get("var1")
        self.assertEqual(result, "configured_value")

    def test_set_from_config_does_nothing_for_missing_key(self):
        self.ctx.set_from_config("missing_var", "value")
        self.assertIsNone(self.ctx.get("missing_var"))

    def test_repr(self):
        self.ctx._set("func1", "var1", "value1", RuntimeContext.PRODUCE)
        repr_str = repr(self.ctx)
        self.assertIn("func1", repr_str)
        self.assertIn("var1", repr_str)
        self.assertIn("value1", repr_str)


if __name__ == '__main__':
    unittest.main()
