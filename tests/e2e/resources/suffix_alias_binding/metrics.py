from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


# The evidence node's canonical id is "rigor:unified_0" — which does NOT contain the
# suffix "e_metric". The suffix only appears in the alias "rigor:r17:e_metric", so the
# function binds only if suffix resolution walks the alias index and returns the
# canonical id. This is the combined issue #93 (aliases) + #94 (suffix) scenario.
@jpipe_link("e_metric")
@jpipe(consume=[], produce=["metrics_reported"])
def report_metrics(produce) -> bool:
    """Evidence: the model reports its metrics."""
    produce("metrics_reported", True)
    return True


@jpipe(consume=["metrics_reported"])
def model_is_rigorous(metrics_reported: bool) -> bool:
    """Conclusion: the model is rigorous when its metrics are reported."""
    return metrics_reported
