import unittest
from unittest.mock import patch

from jpipe_runner.utils.group_loggers import PlainGroupLogger


class TestPlainGroupLogger(unittest.TestCase):
    """
    Test suite for the PlainGroupLogger context manager/decorator.
    Verifies that it defaults to a no-op fallback effectively.
    """

    def test_applies_always_true(self):
        """
        Test that applies() constantly returns True, so this logger
        acts as the fallback when no other conditions are met.
        """
        self.assertTrue(PlainGroupLogger.applies())

    @patch("builtins.print")
    def test_enter_exit(self, mock_print):
        """
        Test the context manager behavior (__enter__ and __exit__).
        Ensures that the plain logger performs no actions or modifications
        to the environment or output when entered and exited.
        """
        logger = PlainGroupLogger()

        returned_logger = logger.__enter__()
        self.assertIs(returned_logger, logger)

        result = logger.__exit__(None, None, None)
        self.assertFalse(result)

        mock_print.assert_not_called()

    @patch("builtins.print")
    def test_decorator_usage(self, mock_print):
        """
        Test the behavior of using the plain logger as a decorator.
        It should not intercept or add anything around the wrapped function.
        """

        @PlainGroupLogger()
        def dummy_function():
            print("Inside function")

        dummy_function()

        mock_print.assert_called_once_with("Inside function")

    def test_context_manager_exception_propagation(self):
        """
        Test that exceptions raised inside the context manager are not swallowed.
        """
        logger = PlainGroupLogger()
        with self.assertRaises(ValueError) as context:
            with logger:
                raise ValueError("Test error")
        self.assertEqual(str(context.exception), "Test error")
