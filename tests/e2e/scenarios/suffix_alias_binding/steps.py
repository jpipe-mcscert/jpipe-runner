"""Step library for suffix_alias_binding.

`e_metric` is a suffix of the alias `rigor:r17:e_metric`, not of the canonical id
`rigor:unified_0`: suffix resolution must search the aliases and land on the canonical
element.
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
