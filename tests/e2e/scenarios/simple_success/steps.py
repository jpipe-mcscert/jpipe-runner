"""Step library for simple_success: one evidence, one conclusion."""

from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, conclusion, evidence

CHECKED_FILE = Path("mock/test_file.txt")


@evidence("E1", produces=["file_exists"])
def check_file_exists() -> Outcome:
    """The file under validation is present."""
    if CHECKED_FILE.is_file():
        return Pass(file_exists=True)
    return Fail(f"{CHECKED_FILE} not found")


@conclusion("C1", consumes=["file_exists"])
def file_is_valid(file_exists: bool) -> Outcome:
    """The file is valid when it exists."""
    return Pass() if file_exists else Fail("the file does not exist")
