"""
jpipe_runner.exceptions
~~~~~~~~~~~~~~~~~~~~~~~

This module contains the set of jPipe Runner's exceptions.
"""

import sys

from jpipe_runner.framework.logger import log_buffer

# https://patorjk.com/software/taag/#p=display&f=Ivrit&t=STDERR%20OUTPUT%20BEGIN
STDERR_OUTPUT_BEGIN = r"""

  _____ ____  ____   ___  ____    _     ___   ____ 
 | ____|  _ \|  _ \ / _ \|  _ \  | |   / _ \ / ___|
 |  _| | |_) | |_) | | | | |_) | | |  | | | | |  _ 
 | |___|  _ <|  _ <| |_| |  _ <  | |__| |_| | |_| |
 |_____|_| \_\_| \_\\___/|_| \_\ |_____\___/ \____|
                                                   

"""

QUIET_MODE = False


def set_quiet_mode(enabled: bool):
    """Enable or disable quiet mode for exception output."""
    global QUIET_MODE
    QUIET_MODE = enabled


class RunnerException(Exception):
    """There was an ambiguous exception that occurred while running the runner."""


class SyntaxException(SyntaxError, RunnerException):
    """A syntax error occurred."""


class InvalidJustificationException(RunnerException):
    """An invalid justification error occurred."""


class JustificationTraverseException(RunnerException):
    """A justification layered traverse error occurred."""


class RuntimeException(RuntimeError, RunnerException):
    """A runtime error of jpipe runner occurred."""


class FunctionException(RunnerException):
    """A justification function error occurred."""


class WorkflowError(Exception):
    """
    Base exception for workflow errors that should terminate execution.
    Also prints the error message to stderr when `handle` is called if a message is provided.
    """

    def __init__(self, message: str | None = None, exit_code: int = 1):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code

    def handle(self):
        """Print the error message to stderr only if it is not None."""
        if self.message is not None:
            print(self.message, file=sys.stderr)


class WorkflowErrorWithLogDump(WorkflowError):
    """A workflow error that also prints the log buffer to stderr on `handle`."""

    def handle(self):
        """Print the error message (if any), then dump the log buffer."""
        super().handle()

        if not QUIET_MODE:
            print(STDERR_OUTPUT_BEGIN, file=sys.stderr)
        log_buffer.dump_to_stderr()


class NoJustificationFileError(WorkflowError):
    """Raised when no justification file argument is provided."""

    def __init__(self):
        super().__init__("No justification json file provided. Please specify a .json file.")


class InvalidJustificationFileError(WorkflowError):
    """Raised when the justification file is not a .json file."""

    def __init__(self):
        super().__init__("The provided justification file is not a .json file.")


class LibraryNotFoundError(WorkflowError):
    """Raised when one or more library paths do not match any files."""

    def __init__(self, not_matched_files: list[str]):
        msg = (
            f"No library found for path(s): {', '.join(not_matched_files)}\n"
            "Please check the provided library paths."
        )
        super().__init__(msg)


class RuntimeInitializationError(WorkflowError):
    """Raised when the Python runtime throws an exception during initialization."""

    def __init__(self, message: str):
        super().__init__(message)


class DryRunError(WorkflowErrorWithLogDump):
    """
    Raised when a dry-run completes but the log buffer contains errors.
    Only prints the log buffer to stderr, without any additional message.
    """

    def __init__(self):
        super().__init__(None)


class StreamOutputNotSupportedError(WorkflowError):
    """Raised when the output path is set to stdout or stderr."""

    def __init__(self):
        super().__init__("Streamed diagram output is not supported yet.")


class UnsupportedOutputFormatError(WorkflowErrorWithLogDump):
    """Raised when an unsupported image export format is provided."""

    def __init__(self, format: str, supported_formats: list[str]):
        super().__init__(
            f"Unsupported output format: {format}. Supported formats are: {', '.join(supported_formats)}"
        )
