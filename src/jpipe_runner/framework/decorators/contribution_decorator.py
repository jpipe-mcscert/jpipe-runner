from typing import Optional, List


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
        # func.positive_contributions = positive
        # func.negative_contributions = negative
        return func

    return decorator
