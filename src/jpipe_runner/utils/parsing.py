"""
jpipe_runner.utils.parsing
~~~~~~~~~~~~~~~~~~~~~~~~~~

Parse raw strings into native Python types (bool, int, float, None, list, dict).
"""

import ast
import json
import re


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
        if (stripped.startswith('"') and stripped.endswith('"')) or (
            stripped.startswith("'") and stripped.endswith("'")
        ):
            return stripped[1:-1]

        # --- Try JSON parsing ---
        try:
            return json.loads(stripped)
        except Exception:
            pass

        # Try hybrid: replace JSON bool/null with Python equivalents
        hybrid = re.sub(r"\btrue\b", "True", stripped, flags=re.IGNORECASE)
        hybrid = re.sub(r"\bfalse\b", "False", hybrid, flags=re.IGNORECASE)
        hybrid = re.sub(r"\bnull\b", "None", hybrid, flags=re.IGNORECASE)
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
