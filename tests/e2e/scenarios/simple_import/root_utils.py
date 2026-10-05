"""A helper module at the root of the scenario, importable through --python-path."""


def get_root_number_a() -> int:
    """Number a, imported when the step library is loaded."""
    return 10


def get_root_number_c() -> int:
    """Number c, imported inside a step, at run time."""
    return 20
