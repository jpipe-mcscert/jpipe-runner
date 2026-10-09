"""The step that `assemble` requires: the strategy it adds above `checked` and `argued`."""

from jpipe_runner import Fail, Outcome, Pass, strategy


@strategy("release:assembleStrategy", consumes=["code_tested", "suite_failures"])
def both_arguments_hold(code_tested: bool, suite_failures: int) -> Outcome:
    """[strategy] Both arguments hold"""
    if code_tested and suite_failures == 0:
        return Pass()
    return Fail("the two arguments disagree on whether the code is tested")
