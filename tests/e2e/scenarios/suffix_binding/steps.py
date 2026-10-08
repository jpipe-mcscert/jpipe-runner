"""Step library for suffix_binding.

The evidence `rigor:r17:e_metric` is bound by its last segment only: segment-suffix
resolution.
"""

from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, conclusion, evidence


@evidence("e_metric", observes={"metrics": "mock/metrics.csv"}, produces=["metrics_reported"])
def report_metrics(metrics: Path) -> Outcome:
    """The model reports its metrics: the metrics file has at least one row."""
    return Pass(metrics_reported=len(metrics.read_text(encoding="utf-8").splitlines()) > 1)


@conclusion("C1", consumes=["metrics_reported"])
def model_is_rigorous(metrics_reported: bool) -> Outcome:
    """The model is rigorous when its metrics are reported."""
    return Pass() if metrics_reported else Fail("the model does not report its metrics")
