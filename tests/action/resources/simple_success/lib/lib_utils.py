def get_magic_number() -> int:
    """
    Return a fixed number (42) for testing imports from the 'lib.lib_utils' module.

    This function is located in the lib/lib_utils.py file and is used to verify
    that modules in nested packages can be imported and called during runtime
    execution (e.g., via 'from lib.lib_utils import get_magic_number').
    """
    return 42
