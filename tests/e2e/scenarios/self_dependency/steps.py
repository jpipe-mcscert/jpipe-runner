"""Step library for self_dependency.

S1 consumes the very variable it produces: nothing can provide `var_a` before S1 runs.
The model itself is acyclic; the defect is in the step library alone.
"""

from jpipe_runner import Fail, Outcome, Pass, conclusion, strategy


@strategy("S1", consumes=["var_a"], produces=["var_a"])
def function_a(var_a: str) -> Outcome:
    """A is refined from itself."""
    return Pass(var_a=f"processed_{var_a}")


@strategy("S2", consumes=["var_a"], produces=["var_b"])
def function_b(var_a: str) -> Outcome:
    """B is derived from A."""
    return Pass(var_b=f"processed_{var_a}")


@conclusion("C1", consumes=["var_a", "var_b"])
def final_check(var_a: str, var_b: str) -> Outcome:
    """Both A and B were derived."""
    return Pass() if var_a and var_b else Fail("A or B is empty")
