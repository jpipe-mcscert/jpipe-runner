"""A helper module in the `steps` package, next to the step library."""


def get_step_number_b() -> int:
    """Number b, imported when the step library is loaded."""
    return 5


def get_step_number_d() -> int:
    """Number d, imported inside a step, at run time."""
    return 2
