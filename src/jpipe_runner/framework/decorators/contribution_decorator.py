from functools import wraps
from typing import Optional, List

from jpipe_runner.framework.context import ctx, RuntimeContext


def contribution(positive: Optional[List[str]] = None, negative: Optional[List[str]] = None):
    """
    Decorator to declare contributions of an evidence or strategy to a goal.

    :param positive: List of variable names that contribute positively to the goal.
    :param negative: List of variable names that contribute negatively to the goal.
    :return: A function decorator.
    """
    positive = positive or []
    negative = negative or []

    def decorator(func):
        ctx.set_contribution(func.__name__, RuntimeContext.NEGATIVE, negative)
        ctx.set_contribution(func.__name__, RuntimeContext.POSITIVE, positive)
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
