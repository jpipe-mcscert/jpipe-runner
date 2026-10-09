"""Steps written against the standalone `tested` model of assemble.jd.

Their ids are the ones the compiler exports for `tested` alone. `assemble` prefixes every
id with the composed model's name, so `tested:suite` binds `readiness:tested:suite`
through the tail of its id. The conclusion `tested:tested` is left unbound: it takes its
status from the strategy, and in the assembled model it is a sub-conclusion.
"""

from pathlib import Path
from xml.etree import ElementTree

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

THRESHOLD = 80.0


@evidence("tested:suite", observes={"report": "mock/junit.xml"}, produces=["suite_passes"])
def the_test_suite_passes(report: Path) -> Outcome:
    """[evidence] The test suite passes"""
    suite = ElementTree.parse(report).getroot()
    failed = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
    if failed == 0:
        return Pass(suite_passes=True)
    return Fail(f"{report}: {failed} tests failed")


@evidence("tested:coverage", observes={"measured": "mock/coverage.txt"}, produces=["coverage"])
def coverage_is_above_80(measured: Path) -> Outcome:
    """[evidence] Coverage is above 80%"""
    coverage = float(measured.read_text(encoding="utf-8"))
    if coverage > THRESHOLD:
        return Pass(coverage=coverage)
    return Fail(f"coverage is {coverage}%, not above {THRESHOLD}%")


@strategy("tested:testing", consumes=["suite_passes", "coverage"])
def the_test_suite_passes_with_high_coverage(suite_passes: bool, coverage: float) -> Outcome:
    """[strategy] The test suite passes with high coverage"""
    if suite_passes and coverage > THRESHOLD:
        return Pass()
    return Fail("the suite failed or coverage is too low")
