"""docs/migration-v3-v4.md shows a v3 library as v4 refuses it, and its port as it runs (#129).

The v3 library on the page stops at its first import, with the message the page quotes,
and the v4 port is the release example's step library, character for character after its
docstring, as the tutorial shows it.
"""

import ast

import pytest

from tests.conftest import REPO_ROOT
from tests.console import blocks

PAGE = (REPO_ROOT / "docs" / "migration-v3-v4.md").read_text(encoding="utf-8")
LIBRARY = REPO_ROOT / "tests" / "e2e" / "scenarios" / "release_example" / "steps.py"


def test_the_page_has_a_v3_library_and_its_port() -> None:
    assert len(blocks(PAGE, "python")) == 2


def test_the_v3_library_stops_at_its_first_import_as_the_page_quotes() -> None:
    v3, _ = blocks(PAGE, "python")
    library = compile(v3, "release_lib.py", "exec")

    with pytest.raises(ImportError) as error:
        exec(library, {})

    assert f"```\nImportError: {error.value}\n```" in PAGE


def test_the_port_is_the_release_example_s_library() -> None:
    source = LIBRARY.read_text(encoding="utf-8")
    docstring = ast.parse(source).body[0]
    assert isinstance(docstring, ast.Expr)
    after = "".join(source.splitlines(keepends=True)[docstring.end_lineno :]).lstrip("\n")

    assert blocks(PAGE, "python")[1] == after
