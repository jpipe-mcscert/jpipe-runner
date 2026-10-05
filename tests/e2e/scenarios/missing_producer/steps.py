"""Step library for missing_producer.

S1 processes the string but never declares `processed_string` among its outputs, so the
conclusion consumes a variable no step produces.
"""

from jpipe_runner import Fail, Outcome, Pass, conclusion, strategy

# v3 injected this through config.yaml; v4 has no injection.
INPUT_STRING = "test"


@strategy("S1")
def process_string() -> Outcome:
    """The input string can be processed."""
    processed = INPUT_STRING.upper()
    return Pass() if processed else Fail("the processed string is empty")


@conclusion("C1", consumes=["processed_string"])
def validate_string(processed_string: str) -> Outcome:
    """The processed string is not empty."""
    return Pass() if processed_string else Fail("the processed string is empty")
