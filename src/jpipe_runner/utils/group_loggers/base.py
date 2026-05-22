from abc import ABC, abstractmethod
from contextlib import ContextDecorator


class GroupLogger(ABC, ContextDecorator):
    """
    Base class for group loggers. A group logger acts as a context manager
    to group logs together in a way that is appropriate for the execution environment (e.g. CI/CD pipelines).

    Inheriting from ContextDecorator allows using this logger either in a `with` block
    or directly as a function decorator (`@get_group_logger()`).
    """

    @classmethod
    @abstractmethod
    def applies(cls) -> bool:
        """
        Return True if this logger should be used in the current environment.
        This method must be implemented by subclasses to determine their applicability.
        """
        pass

    @abstractmethod
    def __enter__(self) -> "GroupLogger":
        """
        Enter the context. This is typically where group tags are started.
        """
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Exit the context. This is typically where group tags are ended.
        """
        pass
