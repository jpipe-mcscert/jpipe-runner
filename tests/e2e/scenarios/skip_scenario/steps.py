"""Step library for skip_scenario: a strategy that declines to run."""

from jpipe_runner import Fail, Outcome, Pass, Skip, conclusion, strategy

# v3 read `enable_feature` from config.yaml and then skipped unconditionally with @skip.
# v4 has neither injection nor @skip: the switch is a constant and the skip is a return value.
FEATURE_ENABLED = False


@strategy("S1", produces=["feature_result"])
def optional_feature() -> Outcome:
    """The optional feature is exercised, when it is enabled."""
    if not FEATURE_ENABLED:
        return Skip("the optional feature is disabled")
    return Pass(feature_result="enabled")


@conclusion("C1", consumes=["feature_result"])
def use_feature_result(feature_result: str) -> Outcome:
    """The feature result can be relied on."""
    if feature_result == "enabled":
        return Pass()
    return Fail(f"unexpected feature result {feature_result!r}")
