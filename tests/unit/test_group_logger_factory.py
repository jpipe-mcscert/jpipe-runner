import os
import unittest
from unittest.mock import patch

from jpipe_runner.utils.group_loggers import (
    GitHubActionsGroupLogger,
    PlainGroupLogger,
    get_group_logger,
)


class TestGetGroupLogger(unittest.TestCase):
    """
    Test suite for the get_group_logger factory function.
    Verifies that the factory selects the correct logger implementation
    based on the current environment configuration.
    """

    @patch.dict(os.environ, {"JPIPE_RUNNER_GROUP_LOGS": "1"}, clear=True)
    def test_get_group_logger_github_actions(self):
        """
        Test that get_group_logger returns a GitHubActionsGroupLogger instance
        when the corresponding environment flags are explicitly enabled.
        """
        logger = get_group_logger()
        self.assertIsInstance(logger, GitHubActionsGroupLogger)

    @patch.dict(os.environ, {}, clear=True)
    def test_get_group_logger_plain(self):
        """
        Test that get_group_logger defaults to returning a PlainGroupLogger instance
        when no special loggers apply to the current environment.
        """
        logger = get_group_logger()
        self.assertIsInstance(logger, PlainGroupLogger)
