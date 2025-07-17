from jpipe_runner.framework.context import ctx


def skip(condition: bool = True, reason: str = "Skipped by condition") -> callable:
    """
    Decorator to skip a function if the condition is True.

    Args:
        condition (bool): Condition to check.
        reason (str): Reason for skipping the function.

    Returns:
        callable: A function decorator that skips the wrapped function if the condition is True.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if condition:
                ctx.set_skip(func.__name__, condition, reason)
            return func(*args, **kwargs)
        return wrapper
    return decorator
