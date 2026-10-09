"""Steps written against the standalone `documented` model of assemble.jd.

`documented:changelog` binds `readiness:documented:changelog` through the tail of its id.
The variable the evidence produces is named after what it means in this model,
`documented_release`, so that it cannot clash with a variable of `tested` once the two
models run together (JP010).
"""

from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy


@evidence(
    "documented:changelog",
    observes={"changelog": "mock/CHANGELOG.md"},
    produces=["documented_release"],
)
def the_changelog_is_up_to_date(changelog: Path) -> Outcome:
    """[evidence] The changelog is up to date"""
    for line in changelog.read_text(encoding="utf-8").splitlines():
        if line.startswith("## ["):
            return Pass(documented_release=line.removeprefix("## [").partition("]")[0])
    return Fail(f"{changelog} documents no release")


@strategy("documented:docs", consumes=["documented_release"])
def the_changelog_and_api_docs_are_current(documented_release: str) -> Outcome:
    """[strategy] The changelog and API docs are current"""
    if documented_release:
        return Pass()
    return Fail("the changelog's latest release has no version")
