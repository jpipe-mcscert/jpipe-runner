"""The project's prose, comments and identifiers use Canadian spelling.

Canadian spelling is ``-our`` (colour, behaviour), ``-re`` (centre), ``-ize`` and ``-yze``
(organize, analyze), a doubled ``l`` (modelled, labelled), ``-ence`` (defence) and
``artifact``. This test flags the British ``-ise`` / ``-yse`` forms and the American
``-or`` / ``-er`` / single-``l`` / ``-ense`` forms in every tracked text file.

Text that is not the project's own is left as it is, and so not checked: third-party
documents kept verbatim, compiler output, mock data, and the keys of external formats.
"""

import re
import subprocess

import pytest

from tests.conftest import REPO_ROOT

NOT_OURS = re.compile(
    r"\.(json|lock|csv|svg|png|pdf|txt)$"
    r"|/mock/"
    r"|^LICENSE$"
    r"|^debian/(changelog|copyright)$"
    r"|^\.github/CODE_OF_CONDUCT\.md$"  # the Contributor Covenant, verbatim
    r"|^action\.yml$"  # GitHub's `branding.color` key
    r"|^tests/unit/test_spelling\.py$"  # this test's own counter-examples
)

# Words ending in -ise that are spelled so in Canadian English too.
ISE_IS_RIGHT = set(
    [
        "raise",
        "raised",
        "raises",
        "raising",
        "otherwise",
        "exercise",
        "exercised",
        "exercises",
        "exercising",
        "precise",
        "promise",
        "promised",
        "promises",
        "likewise",
        "advise",
        "advised",
        "advises",
        "revise",
        "revised",
        "revises",
        "comprise",
        "comprises",
        "comprised",
        "surprise",
        "surprised",
        "surprises",
        "surprising",
        "compromise",
        "expertise",
        "enterprise",
        "premise",
        "premises",
        "concise",
        "noise",
        "arise",
        "arises",
        "arising",
        "devise",
        "devised",
        "supervise",
        "supervised",
        "disguise",
        "praise",
        "praised",
        "cruise",
        "poise",
        "treatise",
        "paradise",
        "clockwise",
        "advertise",
        "advertised",
        "demise",
        "reprise",
        "guise",
        "franchise",
        "rise",
        "rises",
        "wise",
    ]
)
BRITISH = re.compile(r"\b([a-z]+is(?:e|ed|es|ing|ation|ations))\b|\b([a-z]*lys(?:e|ed|ing))\b")
AMERICAN = re.compile(
    r"\b(colou?rs?|colored|coloring|behaviors?|behavioral|favors?|favorite|honors?|labors?"
    r"|neighbors?|centers?|centered|theaters?|defense|offense"
    r"|labeled|labeling|modeled|modeling|traveled|traveling|canceled|canceling)\b"
)


def _ours() -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [path for path in tracked if not NOT_OURS.search(path)]


def _misspellings(text: str) -> list[str]:
    found = []
    for line in text.lower().splitlines():
        for match in BRITISH.finditer(line):
            word = match.group(1) or match.group(2)
            if word not in ISE_IS_RIGHT:
                found.append(word)
        found += [
            m.group(1) for m in AMERICAN.finditer(line) if not m.group(1).startswith("colour")
        ]
    return found


@pytest.mark.parametrize("path", _ours())
def test_spelling_is_canadian(path: str) -> None:
    try:
        text = (REPO_ROOT / path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        pytest.skip("not text")
    assert _misspellings(text) == []


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("the organisation analysed it", ["organisation", "analysed"]),
        ("its color and behavior, centered", ["color", "behavior", "centered"]),
        ("modeled and labeled", ["modeled", "labeled"]),
        ("raise otherwise; organize, analyze, colour, behaviour, centre, modelled", []),
    ],
)
def test_the_check_tells_canadian_from_the_rest(text: str, flagged: list[str]) -> None:
    assert _misspellings(text) == flagged
