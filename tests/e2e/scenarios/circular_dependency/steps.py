"""Step library for circular_dependency.

S1 and S2 support each other in the model (S1 -> S2 -> S1), and each consumes what the
other produces. The runner must reject the model before running anything.
"""

from jpipe_runner import Fail, Outcome, Pass, conclusion, strategy


@strategy("S1", consumes=["var_b"], produces=["var_a"])
def function_a(var_b: str) -> Outcome:
    """A is derived from B."""
    return Pass(var_a=f"processed_{var_b}")


@strategy("S2", consumes=["var_a"], produces=["var_b"])
def function_b(var_a: str) -> Outcome:
    """B is derived from A, which closes the cycle."""
    return Pass(var_b=f"processed_{var_a}")


@conclusion("C1", consumes=["var_a", "var_b"])
def final_check(var_a: str, var_b: str) -> Outcome:
    """Both A and B were derived."""
    return Pass() if var_a and var_b else Fail("A or B is empty")
