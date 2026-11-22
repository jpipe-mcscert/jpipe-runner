"""Steps written against the standalone `documented` model of coverage.jd.

Its evidence produces `coverage` too: the name means documentation coverage here, and
nothing in this library needs to know that `tested_steps.py` uses it as well.
"""

from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

THRESHOLD = 90.0


@evidence(
    "documented:coverage", observes={"measured": "mock/doc-coverage.txt"}, produces=["coverage"]
)
def documentation_coverage_is_measured(measured: Path) -> Outcome:
    """[evidence] Documentation coverage is measured"""
    return Pass(coverage=float(measured.read_text(encoding="utf-8")))


@strategy("documented:docs", consumes=["coverage"])
def documentation_coverage_clears_the_bar(coverage: float) -> Outcome:
    """[strategy] Documentation coverage clears the bar"""
    if coverage > THRESHOLD:
        return Pass()
    return Fail(f"documentation coverage is {coverage}%, not above {THRESHOLD}%")
