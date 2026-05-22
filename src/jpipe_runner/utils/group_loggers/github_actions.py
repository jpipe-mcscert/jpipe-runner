import os

from .base import GroupLogger


class GitHubActionsGroupLogger(GroupLogger):
    """
    Group logger for GitHub Actions environments.

    Automatically wraps execution logs with GitHub Actions group tags
    (``##[group]`` and ``##[endgroup]``) when running in a CI/CD pipeline,
    allowing logs to be collapsed in the GitHub UI.
    """

    @classmethod
    def applies(cls) -> bool:
        """
        Determine if this logger should be used in the current environment.
        If the environment variable ``JPIPE_RUNNER_GROUP_LOGS`` is set to "1", this logger will be used.
        """
        return os.getenv("JPIPE_RUNNER_GROUP_LOGS") == "1"

    def __enter__(self) -> "GitHubActionsGroupLogger":
        """
        Start the GitHub Actions log group.
        """
        print("##[group]Execution logs:", flush=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        End the GitHub Actions log group.
        """
        print("##[endgroup]", flush=True)
        return False  # Don't suppress exceptions, if any occurred within the block
