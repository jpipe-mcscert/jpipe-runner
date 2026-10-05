"""Step library for suffix_binding.

The evidence `rigor:r17:e_metric` is bound by its last segment only: segment-suffix
resolution.
"""

from jpipe_runner import Fail, Outcome, Pass, conclusion, evidence


@evidence("e_metric", produces=["metrics_reported"])
def report_metrics() -> Outcome:
    """The model reports its metrics."""
    return Pass(metrics_reported=True)


@conclusion("C1", consumes=["metrics_reported"])
def model_is_rigorous(metrics_reported: bool) -> Outcome:
    """The model is rigorous when its metrics are reported."""
    return Pass() if metrics_reported else Fail("the model does not report its metrics")
