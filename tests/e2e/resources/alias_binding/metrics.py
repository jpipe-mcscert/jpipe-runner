from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


# The unified evidence node "rigor:unified_0" is bound here by TWO of its aliases
# (neither of which is the canonical id). This exercises both alias resolution and
# stacking multiple @jpipe_link decorators on a single implementing function.
@jpipe_link("rigor:r17:e_metric")
@jpipe_link("rigor:r18:e")
@jpipe(consume=[], produce=["metrics_reported"])
def report_metrics(produce) -> bool:
    """Evidence: the model reports its metrics."""
    produce("metrics_reported", True)
    return True


@jpipe(consume=["metrics_reported"])
def model_is_rigorous(metrics_reported: bool) -> bool:
    """Conclusion: the model is rigorous when its metrics are reported."""
    return metrics_reported
