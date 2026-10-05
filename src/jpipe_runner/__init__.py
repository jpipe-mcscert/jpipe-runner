"""jpipe-runner: execute jPipe justification models against a Python step library."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("jpipe-runner")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"

__all__ = ["__version__"]
