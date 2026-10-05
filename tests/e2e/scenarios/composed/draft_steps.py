"""Steps written against the standalone `draft` model of refine.jd.

Their ids are the ones the compiler exports for `draft` alone (`jpipe process -m draft
-f PYTHON`). In the composed `readiness` model the hook `tests` became the sub-conclusion
`readiness:hook`, and `draft:tests` now reaches it only through its alias
`readiness:draft:tests`. `the_test_suite_passes` is still declared as evidence, so it
runs as an independent cross-check of a claim that `tested` also argues (JP008, a
warning).
"""

from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy


@evidence("draft:tests", produces=["tests_pass"])
def the_test_suite_passes() -> Outcome:
    """[evidence] The test suite passes"""
    if Path("mock/tests.ok").is_file():
        return Pass(tests_pass=True)
    return Fail("mock/tests.ok not found: the test suite did not pass")


@evidence("draft:changelog", produces=["changelog_ok"])
def the_changelog_is_up_to_date() -> Outcome:
    """[evidence] The changelog is up to date"""
    if "2.0" in Path("mock/CHANGELOG.md").read_text(encoding="utf-8"):
        return Pass(changelog_ok=True)
    return Fail("mock/CHANGELOG.md does not name release 2.0")


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
