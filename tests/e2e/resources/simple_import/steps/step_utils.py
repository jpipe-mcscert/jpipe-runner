def get_step_number_b() -> int:
    """
    Return a fixed number (5) for testing imports from the 'steps.step_utils' module.

    This function is located in the steps/step_utils.py file and is used to verify
    that modules in nested packages can be imported and called during runtime execution
    (e.g., via 'from steps.step_utils import get_step_number_b').
    """
    return 5


def get_step_number_d() -> int:
    """
    Return a fixed number (2) for testing imports from the 'steps.step_utils' module.

    Same as get_step_number_b, but used to verify that imports can be done at runtime.
    (e.g., local import 'from steps.step_utils import get_step_number_d' inside a function).
    """
    return 2
