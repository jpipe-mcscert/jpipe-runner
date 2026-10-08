"""Steps written against the standalone `draft` model of refine.jd.

Their ids are the ones the compiler exports for `draft` alone (`jpipe process -m draft
-f PYTHON`). In the composed `readiness` model the hook `tests` became the sub-conclusion
`readiness:hook`, and `draft:tests` now reaches it only through its alias
`readiness:draft:tests`. `the_test_suite_passes` is still declared as evidence, so it
runs as an independent cross-check of a claim that `tested` also argues (JP008, a
warning).
"""

from pathlib import Path
from xml.etree import ElementTree

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy


@evidence("draft:tests", observes={"report": "mock/junit.xml"}, produces=["tests_pass"])
def the_test_suite_passes(report: Path) -> Outcome:
    """[evidence] The test suite passes"""
    suite = ElementTree.parse(report).getroot()
    failed = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
    if failed == 0:
        return Pass(tests_pass=True)
    return Fail(f"{report}: {failed} tests failed")


@evidence("draft:changelog", observes={"changelog": "mock/CHANGELOG.md"}, produces=["changelog_ok"])
def the_changelog_is_up_to_date(changelog: Path) -> Outcome:
    """[evidence] The changelog is up to date"""
    if "2.0" in changelog.read_text(encoding="utf-8"):
        return Pass(changelog_ok=True)
    return Fail(f"{changelog} does not name release 2.0")


@strategy("draft:docs", consumes=["changelog_ok"], produces=["docs_current"])
def the_changelog_and_api_docs_are_current(changelog_ok: bool) -> Outcome:
    """[strategy] The changelog and API docs are current"""
    return Pass(docs_current=changelog_ok)


@strategy("draft:gates", consumes=["tests_pass", "docs_current"])
def all_release_gates_pass(tests_pass: bool, docs_current: bool) -> Outcome:
    """[strategy] All release gates pass"""
    if tests_pass and docs_current:
        return Pass()
    return Fail("a release gate did not pass")
