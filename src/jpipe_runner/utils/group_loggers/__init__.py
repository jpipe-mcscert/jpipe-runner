"""
jpipe_runner.utils.group_loggers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Provides context-manager based group loggers. These detect the execution
environment and safely group log outputs (e.g. for CI/CD interfaces).
"""

from .base import GroupLogger
from .github_actions import GitHubActionsGroupLogger
from .plain import PlainGroupLogger


def get_group_logger() -> GroupLogger:
    """
    Iterate through the available GroupLogger classes and return the first one
    that applies to the current environment context.

    :return: An initialized GroupLogger instance suitable for the environment.
    :rtype: GroupLogger
    """
    logger_classes = [
        GitHubActionsGroupLogger,
        PlainGroupLogger,
    ]

    for cls in logger_classes:
        if cls.applies():
            return cls()
    return (
        PlainGroupLogger()
    )  # fallback, should never reach here due to PlainGroupLogger.applies() always returning True
