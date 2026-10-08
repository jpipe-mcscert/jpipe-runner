"""The examples of docs/authoring.md run as written.

Every ``python`` block of the page is executed, in order, in one namespace, so a later
example may use what an earlier one declared. A block that stops working with the API it
documents fails here.
"""

import re

from tests.conftest import REPO_ROOT

PAGE = (REPO_ROOT / "docs" / "authoring.md").read_text(encoding="utf-8")
BLOCKS = re.findall(r"^```python\n(.*?)^```", PAGE, re.MULTILINE | re.DOTALL)


def test_the_page_has_examples() -> None:
    assert len(BLOCKS) >= 5


def test_every_example_runs() -> None:
    namespace: dict[str, object] = {"__name__": "authoring_doc"}
    for block in BLOCKS:
        exec(compile(block, "docs/authoring.md", "exec"), namespace)
