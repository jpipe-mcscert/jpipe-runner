"""The step that `assemble` requires: the strategy it adds above the two arguments.

It sees both values named `coverage`, one from each sub-argument, so it names the part of
the argument each comes from with `Produced(variable, by=id)`: here, the conclusion of
each source model, which `assemble` turned into a sub-conclusion.
"""

from jpipe_runner import Fail, Outcome, Pass, Produced, strategy

RELEASE_BAR = 80.0


@strategy(
    "readiness:assembleStrategy",
    consumes={
        "tests": Produced("coverage", by="tested:tested"),
        "docs": Produced("coverage", by="documented:documented"),
    },
)
def both_coverages_clear_the_release_bar(tests: float, docs: float) -> Outcome:
    """[strategy] Both coverages clear the release bar"""
    if min(tests, docs) > RELEASE_BAR:
        return Pass()
    return Fail(f"coverage is {tests}% for the tests and {docs}% for the documentation")
