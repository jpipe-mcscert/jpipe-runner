"""The step that `assemble` requires: the strategy it adds on top of the two arguments.

`assemble` adds a strategy, `readiness:assembleStrategy`, and a conclusion above the
conclusions of the models it assembles. Neither source library can implement that
strategy, since neither model has it, and every strategy needs a step (JP005). It judges
what the two arguments establish together: here, that the release the changelog documents
is the one being shipped.
"""

from jpipe_runner import Fail, Outcome, Pass, strategy

RELEASE = "2.0"


@strategy("readiness:assembleStrategy", consumes=["documented_release"])
def all_release_gates_pass(documented_release: str) -> Outcome:
    """[strategy] All release gates pass"""
    if documented_release == RELEASE:
        return Pass()
    return Fail(f"the changelog documents release {documented_release}, not {RELEASE}")
