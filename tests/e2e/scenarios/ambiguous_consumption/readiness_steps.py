"""The strategy `assemble` adds, consuming `coverage` without saying which.

Both sub-arguments below it produce `coverage`, so the name designates two values here,
and the runner does not guess (JP025). `shared_names` is the same library, fixed with
`Produced(variable, by=id)`.
"""

from jpipe_runner import Fail, Outcome, Pass, strategy

RELEASE_BAR = 80.0


@strategy("readiness:assembleStrategy", consumes=["coverage"])
def both_coverages_clear_the_release_bar(coverage: float) -> Outcome:
    """[strategy] Both coverages clear the release bar"""
    if coverage > RELEASE_BAR:
        return Pass()
    return Fail(f"coverage is {coverage}%")
