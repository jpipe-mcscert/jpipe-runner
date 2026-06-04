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
    """Strategy that raises an exception"""
    raise Exception(
        "This is an intentional exception raised by the test to verify that "
        "the action correctly adds the error message to the PR comment."
    )
