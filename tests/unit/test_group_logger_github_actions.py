import os
import unittest
from unittest.mock import call, patch

from jpipe_runner.utils.group_loggers import GitHubActionsGroupLogger


class TestGitHubActionsGroupLogger(unittest.TestCase):
    """
    Test suite for the GitHubActionsGroupLogger context manager/decorator.
    Verifies that it correctly integrates with the GitHub Actions logging system.
    """

    @patch.dict(os.environ, {"JPIPE_RUNNER_GROUP_LOGS": "1"}, clear=True)
    def test_applies_true(self):
        """
        Test that applies() returns True when the JPIPE_RUNNER_GROUP_LOGS environment variable is set to "1".
        This indicates the logger should activate in the current execution environment.
        """
        self.assertTrue(GitHubActionsGroupLogger.applies())

    @patch.dict(os.environ, {"JPIPE_RUNNER_GROUP_LOGS": "0"}, clear=True)
    def test_applies_false_when_zero(self):
        """
        Test that applies() returns False when JPIPE_RUNNER_GROUP_LOGS is explicitly disabled ("0").
        """
        self.assertFalse(GitHubActionsGroupLogger.applies())

    @patch.dict(os.environ, {}, clear=True)
    def test_applies_false_when_not_set(self):
        """
        Test that applies() returns False when JPIPE_RUNNER_GROUP_LOGS is not set at all.
        """
        self.assertFalse(GitHubActionsGroupLogger.applies())

    @patch("builtins.print")
    def test_enter_exit(self, mock_print):
        """
        Test the context manager behavior (__enter__ and __exit__).
        Ensures that entering the context starts a GitHub Actions log group
        and exiting it cleanly closes the log group.
        """
        logger = GitHubActionsGroupLogger()

        returned_logger = logger.__enter__()
        self.assertIs(returned_logger, logger)
        mock_print.assert_called_once_with(GitHubActionsGroupLogger.GROUP_START_TAG, flush=True)

        mock_print.reset_mock()

        result = logger.__exit__(None, None, None)
        self.assertFalse(result)
        mock_print.assert_called_once_with(GitHubActionsGroupLogger.GROUP_END_TAG, flush=True)

    @patch("builtins.print")
    def test_decorator_usage(self, mock_print):
        """
        Test that using the logger as a function decorator automatically wraps
        the function's execution within the GitHub Actions grouping markup.
        """

        @GitHubActionsGroupLogger()
        def dummy_function():
            print("Inside function")

        dummy_function()

        # Verify the correct sequence
        mock_print.assert_has_calls(
            [
                call(GitHubActionsGroupLogger.GROUP_START_TAG, flush=True),
                call("Inside function"),
                call(GitHubActionsGroupLogger.GROUP_END_TAG, flush=True),
            ],
            any_order=False,
        )

    @patch("builtins.print")
    def test_context_manager_exception_propagation(self, mock_print):
        """
        Test that exceptions raised inside the context manager are not swallowed,
        and that the log group is properly closed even when an exception occurs.
        """
        logger = GitHubActionsGroupLogger()
        with self.assertRaises(ValueError) as context:
            with logger:
                raise ValueError("Test error")

        self.assertEqual(str(context.exception), "Test error")
        # Verify the endgroup tag was still printed even on exception
        mock_print.assert_has_calls(
            [
                call(GitHubActionsGroupLogger.GROUP_START_TAG, flush=True),
                call(GitHubActionsGroupLogger.GROUP_END_TAG, flush=True),
            ]
        )

        self.assertEqual(mock_print.call_count, 2)
