"""
jpipe_runner.utils
~~~~~~~~~~~~~~~~~~

This module contains the utilities of jPipe Runner.
"""

import os
import re
import ast
import json

from contextlib import contextmanager

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


@contextmanager
def group_github_logs():
    """Wrap logs around github action logging group tags if running in github action.
    
    See https://github.com/actions/toolkit/blob/main/docs/commands.md#group-and-ungroup-log-lines
    for further details about github action logs grouping and related syntax.
    """
    should_group_logs = os.getenv("JPIPE_RUNNER_GROUP_LOGS") == "1"
    if should_group_logs:
        print("##[group]Execution logs:")
    try:
        yield
    finally:
        if should_group_logs:
            print("##[endgroup]")


def sanitize_string(s: str) -> str:
    # Convert to snake case
    # Ref: https://stackoverflow.com/a/1176023/9243111
    s = re.sub(r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', '_', s).lower()
    # Use re to keep only allowed characters.
    sanitized = re.sub(r'[^a-z0-9_]', '',
                       re.sub(r'\s+', '_',
                              re.sub(r'[/|\\]', ' ', s).strip()))
    return sanitized


def parse_value(raw):
    """
    Convert a raw string or already-parsed object into proper Python types.
    Supports:
    - bools: "true", "True", "false", "False"
    - null/None
    - ints, floats
    - quoted strings
    - lists/dicts in JSON or Python literal syntax
    """
    if isinstance(raw, (bool, int, float, type(None), list, dict)):
        return raw  # already parsed (from YAML, for example)

    if isinstance(raw, str):
        stripped = raw.strip()
        lowered = stripped.lower()

        # --- Boolean ---
        if lowered == "true":
            return True
        if lowered == "false":
            return False

        # --- None/null ---
        if lowered in {"none", "null"}:
            return None

        # --- Try int ---
        if re.fullmatch(r"[+-]?\d+", stripped):
            try:
                return int(stripped)
            except ValueError:
                pass

        # --- Try float ---
        if re.fullmatch(r"[+-]?\d+\.\d+", stripped):
            try:
                return float(stripped)
            except ValueError:
                pass

        # --- Quoted string ---
        if (stripped.startswith('"') and stripped.endswith('"')) or \
           (stripped.startswith("'") and stripped.endswith("'")):
            return stripped[1:-1]

        # --- Try JSON parsing ---
        try:
            return json.loads(stripped)
        except Exception:
            pass


        # Try hybrid: replace JSON bool/null with Python equivalents
        hybrid = re.sub(r'\btrue\b', 'True', stripped, flags=re.IGNORECASE)
        hybrid = re.sub(r'\bfalse\b', 'False', hybrid, flags=re.IGNORECASE)
        hybrid = re.sub(r'\bnull\b', 'None', hybrid, flags=re.IGNORECASE)
        try:
            return ast.literal_eval(hybrid)
        except Exception:
            pass

        # --- Fallback: keep as string ---
        return stripped

    return raw


def normalize_structure(data):
    """
    Recursively normalize all values in dicts/lists using parse_value.
    """
    if isinstance(data, dict):
        return {k: normalize_structure(parse_value(v)) for k, v in data.items()}
    elif isinstance(data, list):
        return [normalize_structure(parse_value(v)) for v in data]
    else:
        return parse_value(data)
