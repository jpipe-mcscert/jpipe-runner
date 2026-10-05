"""Step library for alias_binding.

The unified evidence `rigor:unified_0` is bound through two of its aliases, neither of
which is its canonical id: alias resolution, and several ids on one decorator.
"""

from jpipe_runner import Fail, Outcome, Pass, conclusion, evidence


@evidence("rigor:r17:e_metric", "rigor:r18:e", produces=["metrics_reported"])
def report_metrics() -> Outcome:
    """The model reports its metrics."""
    return Pass(metrics_reported=True)


@conclusion("C1", consumes=["metrics_reported"])
def model_is_rigorous(metrics_reported: bool) -> Outcome:
    """The model is rigorous when its metrics are reported."""
    return Pass() if metrics_reported else Fail("the model does not report its metrics")
