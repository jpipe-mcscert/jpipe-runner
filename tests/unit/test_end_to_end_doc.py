"""docs/end-to-end.md quotes the release example's step library as it is.

Every function of ``tests/e2e/scenarios/release_example/steps.py`` appears in the page,
character for character, so the walkthrough cannot drift from the code the e2e suite runs.
"""

import ast

import pytest

from tests.conftest import REPO_ROOT

PAGE = (REPO_ROOT / "docs" / "end-to-end.md").read_text(encoding="utf-8")
LIBRARY = REPO_ROOT / "tests" / "e2e" / "scenarios" / "release_example" / "steps.py"
SOURCE = LIBRARY.read_text(encoding="utf-8")
FUNCTIONS = [node for node in ast.parse(SOURCE).body if isinstance(node, ast.FunctionDef)]


def test_the_release_library_has_functions_to_quote() -> None:
    assert len(FUNCTIONS) == 3


@pytest.mark.parametrize("function", FUNCTIONS, ids=lambda function: function.name)
def test_the_page_quotes_each_function_verbatim(function: ast.FunctionDef) -> None:
    lines = SOURCE.splitlines()
    first = min(d.lineno for d in function.decorator_list)
    quoted = "\n".join(lines[first - 1 : function.end_lineno])
    assert quoted in PAGE
