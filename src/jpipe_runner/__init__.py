"""jpipe-runner: execute jPipe justification models against a Python step library.

The public API, what a step library imports, is loaded when it is first used, so that
importing the package loads nothing but the standard library: ``python -m jpipe_runner``
imports the package before it can drop the working directory from ``sys.path``, and the
runner's dependencies must not be looked up there.
"""

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jpipe_runner.outcomes import Fail, Outcome, Pass, Skip
    from jpipe_runner.steps import conclusion, evidence, strategy, sub_conclusion

try:
    __version__ = version("jpipe-runner")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"

_PUBLIC = {
    "Fail": "outcomes",
    "Outcome": "outcomes",
    "Pass": "outcomes",
    "Skip": "outcomes",
    "conclusion": "steps",
    "evidence": "steps",
    "strategy": "steps",
    "sub_conclusion": "steps",
}

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


def __getattr__(name: str) -> Any:
    module = _PUBLIC.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(f"jpipe_runner.{module}"), name)
