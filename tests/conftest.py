"""Test-suite wiring shared by every layer.

Markers are derived from the directory a test lives in, so they cannot be forgotten:
everything under ``tests/unit/`` is ``unit`` and everything under ``tests/e2e/`` is
``e2e``. A test anywhere else is a collection error rather than a test that no ``-m``
selection would ever run.
"""

from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).parent
REPO_ROOT = TESTS_ROOT.parent
LAYERS = ("unit", "e2e")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        layer = item.path.relative_to(TESTS_ROOT).parts[0]
        if layer not in LAYERS:
            raise pytest.UsageError(
                f"{item.nodeid}: tests must live under one of "
                f"{', '.join(f'tests/{name}/' for name in LAYERS)}"
            )
        item.add_marker(getattr(pytest.mark, layer))
