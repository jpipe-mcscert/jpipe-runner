"""The project's prose, comments and identifiers use Canadian spelling.

Canadian spelling is ``-our`` (colour, behaviour), ``-re`` (centre), ``-ize`` and ``-yze``
(organize, analyze), a doubled ``l`` (modelled, labelled), ``-ence`` (defence) and
``artifact``. This test flags the British ``-ise`` / ``-yse`` forms and the American
``-or`` / ``-er`` / single-``l`` / ``-ense`` forms in every tracked text file, with their
inflections (``organisational``, ``favored``, ``colorful``, ``centering``).

Words are found inside identifiers too: ``test_normalise_paths`` and ``normaliseRewrites``
are split at underscores and case changes before matching.

Text that is not the project's own is left as it is, and so not checked: third-party
documents kept verbatim, compiler output, mock data, and the keys of external formats.
The names of external conventions are also left as they are, wherever they appear: the
``NO_COLOR`` environment variable, and Graphviz's ``color`` attributes written as
attributes (``fillcolor=``, ``"fontcolor"``).
"""

import re
import subprocess

import pytest

from tests.conftest import REPO_ROOT

NOT_OURS = re.compile(
    r"\.(json|lock|csv|svg|png|pdf)$"
    r"|/mock/"
    r"|^LICENSE$"
    r"|^debian/(changelog|copyright)$"
    r"|^\.github/CODE_OF_CONDUCT\.md$"  # the Contributor Covenant, verbatim
    r"|^action\.yml$"  # GitHub's branding key
    r"|^tests/unit/test_spelling\.py$"  # this test's own counter-examples
)

# A word is a run of ASCII letters: underscores, digits and case changes separate words.
_WORD_START, _WORD_END = r"(?<![a-z])", r"(?![a-z])"


def _family(stems: str, suffixes: str) -> str:
    return rf"{_WORD_START}(?:{stems})(?:{suffixes}){_WORD_END}"


# British -ise, and every inflection: organise, organised, organising, organiser,
# organisation, organisational, organisationally. Not -isable, which "disable" ends in.
_ISE = _family(r"[a-z]+is", r"e|ed|es|ing|er|ers|ation|ations|ational|ationally")
# British -yse: analyse, analysed, analysing, analyser. Not "analyses", which is also
# the plural of "analysis", the same in every spelling.
_YSE = _family(r"[a-z]*lys", r"e|ed|ing|er|ers")
# American -or: color, colors, colored, coloring, colorful, colorless, favorite, behavioral.
_OR = _family(
    r"color|behavior|favor|honor|labor|neighbor|flavor|humor|rumor|harbor|armor|endeavor"
    r"|odor|vapor",
    r"|s|ed|ing|ful|fully|less|al|ally|ite|ites|able|ably|er|ers",
)
# American -er: center, centered, centering, theater, fiber.
_ER = _family(r"center|theater|fiber|somber|caliber", r"|s|ed|ing")
# American single l: labeled, modeling, traveler, canceled.
_SINGLE_L = _family(
    r"label|model|travel|cancel|signal|level|fuel|tunnel|marshal|channel|dial|equal|total",
    r"ed|ing|er|ers",
)
# American -ense: defense, offense, pretense.
_ENSE = _family(r"defense|offense|pretense", r"|s")
MISSPELLED = re.compile("|".join([_ISE, _YSE, _OR, _ER, _SINGLE_L, _ENSE]))

# Words ending in -ise that are spelled so in Canadian English too, given as the base
# form: an inflection is allowed when its base is (raising -> raise).
ISE_IS_RIGHT = {
    "raise", "otherwise", "exercise", "precise", "promise", "likewise", "advise", "revise",
    "comprise", "surprise", "compromise", "expertise", "enterprise", "premise", "concise",
    "noise", "arise", "devise", "supervise", "disguise", "praise", "cruise", "poise",
    "treatise", "paradise", "clockwise", "advertise", "demise", "reprise", "guise",
    "franchise", "rise", "wise", "despise", "chastise", "merchandise", "televise",
    "improvise", "incise", "excise", "circumcise",
    "crise", "irise", "mise",  # crises, irises, miser
}  # fmt: skip


def _base(word: str) -> str:
    """The -ise base of a word: raising -> raise, organisation -> organise."""
    return word[: word.rindex("is")] + "ise"


# External names, spelled as their owners spell them: https://no-color.org, and Graphviz's
# node, edge and graph attributes, as an attribute (followed by `=`) or a quoted key.
EXTERNAL_NAMES = re.compile(
    r"NO_COLOR(?![A-Za-z_])"
    r'|(?<![A-Za-z])(?:fill|font|bg|pen|label)?color(?=\s*=|"\s*:)'
    r'|"(?:fill|font|bg|pen|label)?color"'
)


def _misspellings(text: str) -> list[str]:
    found = []
    for raw in text.splitlines():
        raw = EXTERNAL_NAMES.sub(" ", raw)
        line = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", raw).lower()  # camelCase -> camel case
        for match in MISSPELLED.finditer(line):
            word = match.group(0)
            if _ISE_ONLY.fullmatch(word) and _base(word) in ISE_IS_RIGHT:
                continue
            found.append(word)
    return found


_ISE_ONLY = re.compile(r"[a-z]+is(?:e|ed|es|ing|er|ers|ation|ations|ational|ationally)")


def _ours() -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [path for path in tracked if not NOT_OURS.search(path)]


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
        pytest.param("organise organised organising organiser organisation", ["organise", "organised", "organising", "organiser", "organisation"], id="-ise"),
        pytest.param("organisational organisationally recognises", ["organisational", "organisationally", "recognises"], id="-ise derived"),
        pytest.param("analyse analysed analysing analyser", ["analyse", "analysed", "analysing", "analyser"], id="-yse"),
        pytest.param("color colored colorful colorless favored favorite behavioral", ["color", "colored", "colorful", "colorless", "favored", "favorite", "behavioral"], id="-or"),
        pytest.param("center centered centering theaters", ["center", "centered", "centering", "theaters"], id="-er"),
        pytest.param("labeled modeling traveler canceled", ["labeled", "modeling", "traveler", "canceled"], id="single l"),
        pytest.param("defense offenses", ["defense", "offenses"], id="-ense"),
        pytest.param("test_normalise_paths, normaliseRewrites, _organised", ["normalise", "normalise", "organised"], id="inside identifiers"),
        pytest.param("organize organizational analyze analyses colour colourful favoured behaviour centre centring modelled labelling defence", [], id="Canadian"),
        pytest.param("raise raising otherwise exercising wiser riser crises miser disable", [], id="-ise words that are right"),
        pytest.param("literal laboratory honorary humorous coloration totally levels", [], id="near misses"),
        pytest.param('NO_COLOR=1, fillcolor="#fff", color=red, fontcolor = white, {"color": x}', [], id="external names"),
        pytest.param("the colors of a node, color it, NO_COLORS", ["colors", "color", "colors"], id="external names, near misses"),
    ],
)  # fmt: skip
def test_the_check_tells_canadian_from_the_rest(text: str, flagged: list[str]) -> None:
    assert _misspellings(text) == flagged
