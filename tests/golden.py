"""Golden-file comparison for JSON reports (layer 2, see tests/README.md)."""

import difflib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

UPDATE_HINT = "poetry run pytest -m e2e --update-goldens"


def render(document: Any, *, sort_keys: bool = False) -> str:
    """The canonical text of a golden file: 2-space indented JSON, UTF-8, final newline."""
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=sort_keys) + "\n"


def normalize(document: Any, replacements: Mapping[str, str]) -> Any:
    """Replace run-specific substrings (temporary paths) in every string of ``document``.

    Keys are left alone: a report's keys are names, never paths. Longer needles are
    replaced first, so a path and one of its prefixes can both be listed.
    """
    needles = sorted(replacements, key=len, reverse=True)

    def visit(node: Any) -> Any:
        if isinstance(node, str):
            for needle in needles:
                node = node.replace(needle, replacements[needle])
            return node
        if isinstance(node, list):
            return [visit(item) for item in node]
        if isinstance(node, dict):
            return {key: visit(value) for key, value in node.items()}
        return node

    return visit(document)


def assert_matches_golden(actual: Any, golden: Path, *, update: bool) -> None:
    """Compare ``actual`` with the JSON document in ``golden``, or rewrite it if ``update``.

    Documents are compared as data, so key order does not matter but list order does.
    On a mismatch the failure shows a unified diff of both documents with sorted keys.
    """
    if update:
        golden.write_text(render(actual), encoding="utf-8")
        return
    if not golden.exists():
        pytest.fail(f"no golden file at {golden}. Create it with `{UPDATE_HINT}`, then review it.")
    expected = json.loads(golden.read_text(encoding="utf-8"))
    if expected == actual:
        return
    diff = difflib.unified_diff(
        render(expected, sort_keys=True).splitlines(keepends=True),
        render(actual, sort_keys=True).splitlines(keepends=True),
        fromfile=f"{golden.name} (expected)",
        tofile="actual",
    )
    pytest.fail(
        f"report differs from {golden}:\n{''.join(diff)}\n"
        f"If the change is intended, run `{UPDATE_HINT}` and review the diff.",
        pytrace=False,
    )
