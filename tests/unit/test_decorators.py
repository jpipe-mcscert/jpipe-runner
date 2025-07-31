import unittest
from unittest.mock import patch

from jpipe_runner.framework.context import ctx, RuntimeContext
from jpipe_runner.framework.decorators.jpipe_decorator import ConsumedVariableChecker, ProducedVariableChecker, jpipe


class TestConsumedVariableChecker(unittest.TestCase):
    def setUp(self):
        self.ctx_backup = ctx._vars.copy()
        ctx._vars.clear()

    def tearDown(self):
        ctx._vars = self.ctx_backup

    def sample_func(self, a, b):
        return a + b

    def test_register_variables_adds_vars_to_context(self):
        checker = ConsumedVariableChecker(self.sample_func, ("a", "b"))
        checker.register_variables()
        self.assertTrue(ctx.has("sample_func", "a"))
        self.assertTrue(ctx.has("sample_func", "b"))

    def test_inject_arguments_injects_values(self):
        checker = ConsumedVariableChecker(self.sample_func, ("a",))
        checker.register_variables()
        ctx.set("a", 10)
        kwargs = {}
        new_kwargs = checker.inject_arguments(kwargs)
        self.assertIn("a", new_kwargs)
        self.assertEqual(new_kwargs["a"], 10)

    def test_inject_arguments_raises_if_value_none(self):
        checker = ConsumedVariableChecker(self.sample_func, ("a",))
        checker.register_variables()
        # value is None by default (not set)
        with self.assertRaises(ValueError):
            checker.inject_arguments({})

    def test_inject_arguments_warns_for_unused_param(self):
        def func(x):  # declares 'a' but does not use it
            return x

        checker = ConsumedVariableChecker(func, ("a",))
        checker.register_variables()
        ctx._set("func", "a", 123, RuntimeContext.CONSUME)
        ctx.set("a", 123)
        with patch("jpipe_runner.framework.validators.GLOBAL_LOGGER.warning") as mock_warn:
            checker.inject_arguments({})
            mock_warn.assert_called_with(
                "Consumed variable 'a' is declared but not used in function 'func'."
            )

    def test_get_used_variables_returns_correct_vars(self):
        def f(x, y):
            return x + y

        checker = ConsumedVariableChecker(f, ("x", "y"))
        used_vars = checker._get_used_variables()
        self.assertIn("x", used_vars)
        self.assertIn("y", used_vars)


class TestProducedVariableChecker(unittest.TestCase):
    def setUp(self):
        self.ctx_backup = ctx._vars.copy()
        ctx._vars.clear()

    def tearDown(self):
        ctx._vars = self.ctx_backup

    def sample_func(self):
        pass

    def test_register_variables_adds_vars_to_context(self):
        checker = ProducedVariableChecker(self.sample_func, ("out1", "out2"))
        checker.register_variables()
        self.assertTrue(ctx.has("sample_func", "out1") or ctx.has("sample_func", "out2"))

    def test_produce_sets_value_and_tracks_produced(self):
        checker = ProducedVariableChecker(self.sample_func, ("out",))
        checker.register_variables()
        checker.produce("out", 42)
        self.assertIn("out", checker.produced_set)
        self.assertEqual(ctx.get("out"), 42)

    def test_produce_raises_if_undeclared_variable(self):
        checker = ProducedVariableChecker(self.sample_func, ("out",))
        checker.register_variables()
        with self.assertRaises(RuntimeError):
            checker.produce("not_declared", 5)

    def test_validate_produced_raises_if_missing_vars(self):
        checker = ProducedVariableChecker(self.sample_func, ("out1", "out2"))
        checker.register_variables()
        checker.produce("out1", 10)
        with self.assertRaises(RuntimeError):
            checker.validate_produced()

    def test_validate_produced_passes_if_all_produced(self):
        checker = ProducedVariableChecker(self.sample_func, ("out",))
        checker.register_variables()
        checker.produce("out", 5)
        # Should not raise
        checker.validate_produced()


class TestConsumeDecorator(unittest.TestCase):
    def setUp(self):
        self.ctx_backup = ctx._vars.copy()
        ctx._vars.clear()

    def tearDown(self):
        ctx._vars = self.ctx_backup

    def test_consume_decorator_injects_vars(self):
        @jpipe(consume=["val"])
        def func(val):
            return val * 2

        ctx._set("func", "val", 3, RuntimeContext.CONSUME)
        ctx.set("val", 3)
        result = func()
        self.assertEqual(result, 6)

    def test_consume_decorator_raises_if_var_not_set(self):
        @jpipe(consume=["val"])
        def func(val):
            return val

        ctx._set("func", "val", None, RuntimeContext.CONSUME)
        # val not set in context, should raise ValueError
        with self.assertRaises(ValueError):
            func()


class TestProduceDecorator(unittest.TestCase):
    def setUp(self):
        self.ctx_backup = ctx._vars.copy()
        ctx._vars.clear()

    def tearDown(self):
        ctx._vars = self.ctx_backup

    def test_produce_decorator_produces_vars_and_validates(self):
        @jpipe(produce=["out"])
        def func(produce):
            produce("out", 123)
            return "done"

        ctx._set("func", "out", None, RuntimeContext.PRODUCE)
        result = func()
        self.assertEqual(result, "done")
        self.assertEqual(ctx.get("out"), 123)

    def test_produce_decorator_raises_if_undeclared_var_produced(self):
        @jpipe(produce=["out"])
        def func(produce):
            produce("not_declared", 1)  # Should raise

        ctx._set("func", "out", None, RuntimeContext.PRODUCE)
        with self.assertRaises(RuntimeError):
            func()

    def test_produce_decorator_raises_if_not_all_vars_produced(self):
        @jpipe(produce=["out1", "out2"])
        def func(produce):
            produce("out1", 1)
            # Missing out2

        ctx._set("func", "out1", None, RuntimeContext.PRODUCE)
        ctx._set("func", "out2", None, RuntimeContext.PRODUCE)
        with self.assertRaises(RuntimeError):
            func()


if __name__ == "__main__":
    unittest.main()
