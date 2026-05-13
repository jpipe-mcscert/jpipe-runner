def get_root_number_a() -> int:
    """
    Return a fixed number (10) for testing imports from the 'root_utils' module.

    This function is located in the root_utils.py file at the top-level directory
    and is used to verify that modules placed in the root directory can be
    imported and called during runtime execution
    (e.g., via 'from root_utils import get_root_number_a').
    """
    return 10
