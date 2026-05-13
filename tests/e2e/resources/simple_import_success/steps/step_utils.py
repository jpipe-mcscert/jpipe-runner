def get_step_number_b() -> int:
    """
    Return a fixed number (5) for testing imports from the 'steps.step_utils' module.

    This function is located in the steps/step_utils.py file and is used to verify
    that modules in nested packages can be imported and called during runtime execution
    (e.g., via 'from steps.step_utils import get_step_number_b').
    """
    return 5
