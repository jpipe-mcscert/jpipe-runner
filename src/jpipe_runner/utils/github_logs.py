"""
jpipe_runner.utils.github_logs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

GitHub Actions log grouping helpers.
"""

import os
from contextlib import contextmanager


@contextmanager
def group_github_logs():
    """Wrap logs around github action logging group tags if running in github action.

    See https://github.com/actions/toolkit/blob/main/docs/commands.md#group-and-ungroup-log-lines
    for further details about github action logs grouping and related syntax.
    """
    should_group_logs = os.getenv("JPIPE_RUNNER_GROUP_LOGS") == "1"
    if should_group_logs:
        print("##[group]Execution logs:")
    try:
        yield
    finally:
        if should_group_logs:
            print("##[endgroup]")
