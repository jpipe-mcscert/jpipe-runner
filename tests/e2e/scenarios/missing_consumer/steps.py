"""Step library for missing_consumer.

S1 produces `total`, which nothing consumes: the conclusion is not bound.
"""

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

EXPECTED_TOTAL = 15


@evidence("E1", produces=["number_a"])
def generate_number_a() -> Outcome:
    """The first number is available."""
    return Pass(number_a=10)


@evidence("E2", produces=["number_b"])
def generate_number_b() -> Outcome:
    """The second number is available."""
    return Pass(number_b=5)


@strategy("S1", consumes=["number_a", "number_b"], produces=["total"])
def add_numbers(number_a: int, number_b: int) -> Outcome:
    """The two numbers add up to the expected total."""
    total = number_a + number_b
    if total == EXPECTED_TOTAL:
        return Pass(total=total)
    return Fail(f"the numbers add up to {total}, not {EXPECTED_TOTAL}")
