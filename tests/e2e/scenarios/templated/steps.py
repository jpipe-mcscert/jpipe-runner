"""The step library of readiness, which implements the template quality.

The template's conclusion and strategy (quality:ready, quality:gates) are inherited, and
the two @supports it declares are filled by sub-conclusions of readiness. The step of the
sub-conclusion quality:tested produces the value the template's strategy consumes.
"""

from pathlib import Path
from xml.etree import ElementTree

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy, sub_conclusion

RELEASE = "2.0"
THRESHOLD = 80


@evidence("readiness:suite", observes={"report": "mock/junit.xml"}, produces=["tests_pass"])
def the_test_suite_passes(report: Path) -> Outcome:
    """[evidence] The test suite passes"""
    suite = ElementTree.parse(report).getroot()
    failed = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
    if failed == 0:
        return Pass(tests_pass=True)
    return Fail(f"{report}: {failed} tests failed")


@evidence("readiness:coverage", observes={"figure": "mock/coverage.txt"}, produces=["coverage"])
def coverage_is_above_80(figure: Path) -> Outcome:
    """[evidence] Coverage is above 80%"""
    value = int(figure.read_text(encoding="utf-8"))
    if value > THRESHOLD:
        return Pass(coverage=value)
    return Fail(f"coverage is {value}%, not above {THRESHOLD}%")


@strategy("readiness:testing", consumes=["tests_pass", "coverage"])
def the_suite_passes_with_high_coverage(tests_pass: bool, coverage: int) -> Outcome:
    """[strategy] The test suite passes with high coverage"""
    if tests_pass and coverage > THRESHOLD:
        return Pass()
    return Fail("the suite fails, or its coverage is too low")


@sub_conclusion("readiness:quality:tested", produces=["tested"])
def the_code_is_tested() -> Outcome:
    """[sub-conclusion] The code is tested"""
    return Pass(tested=True)


@evidence(
    "readiness:changelog", observes={"changelog": "mock/CHANGELOG.md"}, produces=["changelog_ok"]
)
def the_changelog_is_up_to_date(changelog: Path) -> Outcome:
    """[evidence] The changelog is up to date"""
    if RELEASE in changelog.read_text(encoding="utf-8"):
        return Pass(changelog_ok=True)
    return Fail(f"{changelog} does not name release {RELEASE}")


@strategy("readiness:docs", consumes=["changelog_ok"])
def the_docs_are_current(changelog_ok: bool) -> Outcome:
    """[strategy] The changelog and API docs are current"""
    return Pass() if changelog_ok else Fail("the changelog is stale")


@strategy("readiness:quality:gates", consumes=["tested"])
def all_release_gates_pass(tested: bool) -> Outcome:
    """[strategy] All release gates pass"""
    return Pass() if tested else Fail("the code is not tested")
