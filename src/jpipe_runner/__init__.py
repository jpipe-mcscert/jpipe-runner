"""jpipe-runner: execute jPipe justification models against a Python step library."""

from importlib.metadata import PackageNotFoundError, version

from jpipe_runner.outcomes import Fail, Outcome, Pass, Skip
from jpipe_runner.steps import conclusion, evidence, strategy, sub_conclusion

try:
    __version__ = version("jpipe-runner")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"

__all__ = [
    "Fail",
    "Outcome",
    "Pass",
    "Skip",
    "__version__",
    "conclusion",
    "evidence",
    "strategy",
    "sub_conclusion",
]
