"""Step library for missing_consumer.

S1 produces `total`, which nothing consumes: the conclusion is not bound.
"""

from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

EXPECTED_TOTAL = 15


@evidence("E1", observes={"source": "mock/number_a.txt"}, produces=["number_a"])
def generate_number_a(source: Path) -> Outcome:
    """The first number is available."""
    return Pass(number_a=int(source.read_text(encoding="utf-8")))


@evidence("E2", observes={"source": "mock/number_b.txt"}, produces=["number_b"])
def generate_number_b(source: Path) -> Outcome:
    """The second number is available."""
    return Pass(number_b=int(source.read_text(encoding="utf-8")))


@strategy("S1", consumes=["number_a", "number_b"], produces=["total"])
def add_numbers(number_a: int, number_b: int) -> Outcome:
    """The two numbers add up to the expected total."""
    total = number_a + number_b
    if total == EXPECTED_TOTAL:
        return Pass(total=total)
    return Fail(f"the numbers add up to {total}, not {EXPECTED_TOTAL}")
