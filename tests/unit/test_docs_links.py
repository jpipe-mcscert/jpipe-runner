"""The documentation hangs together: every page is in the index, and every link resolves (#142).

``docs/README.md`` lists the pages of ``docs/`` in reading order, so that a page cannot be
added without a place in it. Every relative link of the README and of ``docs/``, ADRs
included, names a file that exists, and an anchor that one of its headings makes, as GitHub
makes them. So does a link to a file on this repository's ``main`` branch, which the README
uses so that its links work on PyPI too: it names the file in the working tree.
"""

import re
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT

DOCS = REPO_ROOT / "docs"
INDEX = DOCS / "README.md"
PAGES = sorted([REPO_ROOT / "README.md", *DOCS.glob("*.md"), *(DOCS / "adr").glob("*.md")])

_LINK = re.compile(r"\]\((?P<target>[^)\s]+)\)")
# A link to this repository's main branch names a file of the working tree.
_OWN = re.compile(r"https://github\.com/jpipe-mcscert/jpipe-runner/(?:blob|tree)/main/")
_HEADING = re.compile(r"^#{1,6} (?P<title>.+)$", re.MULTILINE)
_FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


def _anchor(title: str) -> str:
    """The anchor GitHub gives a heading: lower case, punctuation dropped, spaces as ``-``."""
    return re.sub(r"[^\w\- ]", "", title.strip().lower()).replace(" ", "-")


def _anchors(page: Path) -> set[str]:
    text = _FENCE.sub("", page.read_text(encoding="utf-8"))
    return {_anchor(match["title"]) for match in _HEADING.finditer(text)}


def _links(page: Path) -> list[str]:
    text = _FENCE.sub("", page.read_text(encoding="utf-8"))
    targets = [_OWN.sub(_to_root(page), match["target"]) for match in _LINK.finditer(text)]
    return [target for target in targets if not re.match(r"[a-z]+:", target)]


def _to_root(page: Path) -> str:
    """The relative path from ``page`` to the root of the repository, ending in ``/``."""
    return "../" * len(page.parent.relative_to(REPO_ROOT).parts)


def test_the_index_lists_every_page_of_docs() -> None:
    listed = {target.split("#")[0] for target in _links(INDEX)}
    pages = {page.name for page in DOCS.glob("*.md") if page != INDEX}

    assert pages <= listed


@pytest.mark.parametrize("page", PAGES, ids=lambda page: str(page.relative_to(REPO_ROOT)))
def test_every_relative_link_resolves(page: Path) -> None:
    broken = []
    for target in _links(page):
        path, _, anchor = target.partition("#")
        linked = (page.parent / path).resolve() if path else page
        if not linked.exists() or (
            anchor and linked.suffix == ".md" and anchor not in _anchors(linked)
        ):
            broken.append(target)

    assert broken == []
