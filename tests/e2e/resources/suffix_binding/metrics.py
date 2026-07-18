from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


# The evidence node has the hierarchical id "rigor:r17:e_metric" but is bound here by
# only its trailing segment "e_metric". This exercises segment-suffix resolution: the
# short, context-free annotation still binds the fully-qualified node, enabling reuse
# of the same logic across contexts.
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
