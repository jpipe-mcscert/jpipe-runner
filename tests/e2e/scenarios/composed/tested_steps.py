"""Steps written against the standalone `tested` model of refine.jd.

Its conclusion `tested:tested` is deliberately left unbound: in the composed model it is
the same element as the hook, which draft_steps.py already binds through `draft:tests`.
Binding it here too would be a conflict (JP007), not a cross-check.
"""

from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

THRESHOLD = 80.0


@evidence("tested:suite", produces=["suite_passes"])
def the_test_suite_passes() -> Outcome:
    """[evidence] The test suite passes"""
    if Path("mock/tests.ok").is_file():
        return Pass(suite_passes=True)
    return Fail("mock/tests.ok not found: the test suite did not pass")


@evidence("tested:coverage", produces=["coverage"])
def coverage_is_above_80() -> Outcome:
    """[evidence] Coverage is above 80%"""
    coverage = float(Path("mock/coverage.txt").read_text(encoding="utf-8"))
    if coverage > THRESHOLD:
        return Pass(coverage=coverage)
    return Fail(f"coverage is {coverage}%, not above {THRESHOLD}%")


@strategy("tested:testing", consumes=["suite_passes", "coverage"])
def the_test_suite_passes_with_high_coverage(suite_passes: bool, coverage: float) -> Outcome:
    """[strategy] The test suite passes with high coverage"""
    if suite_passes and coverage > THRESHOLD:
        return Pass()
    return Fail("the suite failed or coverage is too low")
