import unittest
from unittest.mock import patch

from jpipe_runner.framework.context import ctx, RuntimeContext
from jpipe_runner.framework.decorators.jpipe_decorator import ConsumedVariableChecker, ProducedVariableChecker, jpipe
from jpipe_runner.framework.logger import log_buffer


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

    def test_inject_arguments_logs_error_if_value_none(self):
        log_buffer.logs.clear()

        checker = ConsumedVariableChecker(self.sample_func, ("a",))
        checker.register_variables()
        # No value set for 'a' in context, so it will be None

        checker.inject_arguments({})  # Should log an error

        matching_logs = [
            log for log in log_buffer.logs
            if "has not been set in context before calling" in log and "a" in log
        ]
        self.assertTrue(
            matching_logs,
            "Expected error log about missing consumed variable 'a' not found."
        )

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

    def test_produce_logs_error_if_undeclared_variable(self):
        # Clear previous logs
        log_buffer.logs.clear()

        checker = ProducedVariableChecker(self.sample_func, ("out",))
        checker.register_variables()
        checker.produce("not_declared", 5)

        # Check that an error was logged about producing an undeclared variable
        matching_logs = [
            log for log in log_buffer.logs
            if "attempted to produce undeclared variable" in log and "not_declared" in log
        ]
        self.assertTrue(matching_logs, "Expected error log about undeclared produced variable not found.")

    def test_validate_produced_logs_error_if_missing_vars(self):
        # Clear previous logs
        log_buffer.logs.clear()

        checker = ProducedVariableChecker(self.sample_func, ("out1", "out2"))
        checker.register_variables()
        checker.produce("out1", 10)

        checker.validate_produced()

        # Check that an error was logged about missing variable(s)
        matching_logs = [log for log in log_buffer.logs if "did not produce the following declared variable(s)" in log]
        self.assertTrue(matching_logs, "Expected error log about missing produced variables not found.")

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

    def test_consume_decorator_logs_error_if_var_not_set(self):
        log_buffer.logs.clear()

        @jpipe(consume=["val"])
        def func(val):
            return val

        ctx._set("func", "val", None, RuntimeContext.CONSUME)
        func()  # Should log error instead of raising

        matching_logs = [
            log for log in log_buffer.logs
            if "Consumed variable 'val' has not been set in context before calling 'func'" in log  # Adjust based on your logger message
        ]
        self.assertTrue(
            matching_logs,
            "Expected error log about missing consumed variable 'val' not found."
        )


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

    def test_produce_decorator_logs_error_if_undeclared_var_produced(self):
        # Clear previous logs
        log_buffer.logs.clear()

        @jpipe(produce=["out"])
        def func(produce):
            produce("not_declared", 1)  # Should log an error

        ctx._set("func", "out", None, RuntimeContext.PRODUCE)
        func()

        matching_logs = [
            log for log in log_buffer.logs
            if "attempted to produce undeclared variable" in log and "not_declared" in log
        ]

        self.assertTrue(
            matching_logs,
            "Expected error log for undeclared produced variable 'not_declared' not found."
        )

    def test_produce_decorator_logs_error_if_not_all_vars_produced(self):
        # Clear logs before running
        log_buffer.logs.clear()

        @jpipe(produce=["out1", "out2"])
        def func(produce):
            produce("out1", 1)  # Missing 'out2'

        ctx._set("func", "out1", None, RuntimeContext.PRODUCE)
        ctx._set("func", "out2", None, RuntimeContext.PRODUCE)

        func()  # Should log error instead of raising

        matching_logs = [
            log for log in log_buffer.logs
            if "did not produce the following declared variable(s):" in log and "out2" in log
        ]
        self.assertTrue(
            matching_logs,
            "Expected error log about missing produced variable 'out2' not found."
        )


if __name__ == "__main__":
    unittest.main()
