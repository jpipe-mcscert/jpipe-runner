from .base import GroupLogger


class PlainGroupLogger(GroupLogger):
    """
    A fallback group logger that performs no operations.

    This logger is used when no other environment-specific
    group logger applies to the current execution context.
    """

    @classmethod
    def applies(cls) -> bool:
        """
        This logger applies if no other loggers apply.
        Always returns True.
        """
        return True

    def __enter__(self) -> "PlainGroupLogger":
        """
        Enter the context. This logger does not perform any grouping, so this is a no-op.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Exit the context. This logger does not perform any grouping, so this is a no-op.
        """
        return False  # Don't suppress exceptions, if any occurred within the block
