"""
jpipe_runner.exceptions
~~~~~~~~~~~~~~~~~~~~~~~

This module contains the set of jPipe Runner's exceptions.
"""


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
