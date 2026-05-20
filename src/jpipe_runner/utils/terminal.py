"""
jpipe_runner.utils.terminal
~~~~~~~~~~~~~~~~~~~~~~~~~~~

ANSI-colored terminal output utilities.
"""

# ANSI color codes
COLOR_CODES = {
    "red": "\033[91m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "reset": "\033[0m",
}


def colored(text, color=None, attrs=None):
    """
    A simplified version of termcolor.colored using ANSI escape codes.
    - color: string, like 'red', 'green', etc.
    - attrs: ignored for now or can add bold support
    """
    if color:
        return f"{COLOR_CODES.get(color, '')}{text}{COLOR_CODES['reset']}"
    return text  # no color applied
