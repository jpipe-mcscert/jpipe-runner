"""Steps written against the standalone `tested` model of coverage.jd.

Its evidence produces `coverage`, the name that `documented_steps.py`, written apart, gives
its own value. Each strategy consumes the `coverage` produced below it: a consumed
variable resolves among its consumer's supporters (ADR-0031), so the two never meet here.
"""

from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

THRESHOLD = 80.0


@evidence("tested:coverage", observes={"measured": "mock/coverage.txt"}, produces=["coverage"])
def test_coverage_is_measured(measured: Path) -> Outcome:
    """[evidence] Test coverage is measured"""
    return Pass(coverage=float(measured.read_text(encoding="utf-8")))


@strategy("tested:testing", consumes=["coverage"])
def test_coverage_clears_the_bar(coverage: float) -> Outcome:
    """[strategy] Test coverage clears the bar"""
    if coverage > THRESHOLD:
        return Pass()
    return Fail(f"test coverage is {coverage}%, not above {THRESHOLD}%")
