"""
This test intentionally raises an exception during module import to verify that
the action correctly reports top-level import failures in the PR comment.
"""

from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link

raise ValueError(
    "This is an intentional exception raised during import to verify that the action "
    "correctly adds the error message to the PR comment."
)


@jpipe_link("E1")
@jpipe(produce=["value"])
def test_evidence(produce) -> bool:
    """Unreachable evidence step kept for the same fixture structure."""
    produce("value", 42)
    return True


@jpipe_link("S1")
@jpipe(consume=["value"])
def import_exception_should_fail(value) -> bool:
    """Unreachable strategy step kept for consistency with the other fixtures."""
    return value == 42
