"""
Minimal pipeline for the test-embed-image integration test.

This pipeline exists solely to generate a diagram for the
test-embed-image job in .github/workflows/test-action.yml.

It is intentionally minimal. The diagram output does not matter
what matters is that the action correctly embeds the generated
diagram in the PR comment.
"""

from jpipe_runner.framework.decorators.jpipe_decorator import jpipe
from jpipe_runner.framework.decorators.link_decorator import jpipe_link


@jpipe_link("E1")
@jpipe(produce=["result"])
def simple_evidence(produce) -> bool:
    """Simple evidence that always succeeds."""
    produce("result", True)
    return True


@jpipe_link("C1")
@jpipe(consume=["result"])
def everything_is_ok(result: bool) -> bool:
    """Conclusion — the pipeline succeeded."""
    return result
