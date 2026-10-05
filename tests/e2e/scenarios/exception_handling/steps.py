"""Step library for exception_handling.

S1 raises ZeroDivisionError. The runner records the exception as a FAIL of S1, skips
the conclusion, and reports the justification as failed.
"""

from jpipe_runner import Fail, Outcome, Pass, conclusion, strategy

NUMERATOR = 100
# v3 injected the denominator through config.yaml or --variable; v4 has no injection.
DENOMINATOR = 0


@strategy("S1", produces=["result"])
def divide_by_number() -> Outcome:
    """The numerator can be divided by the denominator."""
    return Pass(result=NUMERATOR / DENOMINATOR)


@conclusion("C1", consumes=["result"])
def validate_division_result(result: float) -> Outcome:
    """The division result is positive."""
    return Pass() if result > 0 else Fail(f"the division result {result} is not positive")
