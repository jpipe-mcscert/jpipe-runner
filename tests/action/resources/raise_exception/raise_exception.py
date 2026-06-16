"""
This test defines a simple pipeline that intentionally raises an exception
to verify that the action correctly captures and reports errors in the PR comment.
"""

from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


@jpipe_link("E1")
@jpipe(produce=["value"])
def test_evidence(produce) -> bool:
    """Simple evidence function"""
    produce("value", 42)
    return True


@jpipe_link("S1")
@jpipe(consume=["value"])
def raise_exception(value) -> bool:
    """
    Intentionally raise an exception to verify pipeline failure reporting.
    """
    raise Exception(
        "This is an intentional exception raised by the test to verify that "
        "the action correctly adds the error message to the PR comment."
    )
    return value == 42  # This line is never reached, but it satisfies the @jpipe consume validation
