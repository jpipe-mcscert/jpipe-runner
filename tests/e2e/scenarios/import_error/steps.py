"""Step library for import_error: simple_success's library, with an import that fails."""

from pathlib import Path

import this_module_does_not_exist  # noqa: F401

from jpipe_runner import Fail, Outcome, Pass, conclusion, evidence


@evidence("E1", observes={"checked": "mock/test_file.txt"}, produces=["file_exists"])
def check_file_exists(checked: Path) -> Outcome:
    """The file under validation is present."""
    return Pass(file_exists=checked.is_file())


@conclusion("C1", consumes=["file_exists"])
def file_is_valid(file_exists: bool) -> Outcome:
    """The file is valid when it exists."""
    return Pass() if file_exists else Fail("the file does not exist")
