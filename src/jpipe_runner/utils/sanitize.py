"""
jpipe_runner.utils.sanitize
~~~~~~~~~~~~~~~~~~~~~~~~~~~

String sanitization helpers.
"""

import re


def sanitize_string(s: str) -> str:
    # Convert to snake case
    # Ref: https://stackoverflow.com/a/1176023/9243111
    s = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", s).lower()
    # Use re to keep only allowed characters.
    sanitized = re.sub(r"[^a-z0-9_]", "", re.sub(r"\s+", "_", re.sub(r"[/|\\]", " ", s).strip()))
    return sanitized
