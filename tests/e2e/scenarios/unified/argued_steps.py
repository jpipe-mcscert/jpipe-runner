"""Steps written against the standalone `argued` model of dominance.jd.

Every id binds through the tail of its prefixed id (`argued:suite` binds
`release:argued:suite`). The sub-conclusion `argued:tested` is left unbound: in the
composed model it is `release:unified_0`, which checked_steps.py binds through
`checked:tests`. Binding it here too would be two functions for one element (JP007).
"""

from pathlib import Path
from xml.etree import ElementTree

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy


@evidence("argued:suite", observes={"report": "mock/junit.xml"}, produces=["suite_failures"])
def the_test_suite_passes(report: Path) -> Outcome:
    """[evidence] The test suite passes"""
    suite = ElementTree.parse(report).getroot()
    return Pass(suite_failures=int(suite.get("failures", "0")) + int(suite.get("errors", "0")))


@strategy("argued:testing", consumes=["suite_failures"])
def the_test_suite_passes_with_high_coverage(suite_failures: int) -> Outcome:
    """[strategy] The test suite passes with high coverage"""
    if suite_failures == 0:
        return Pass()
    return Fail(f"{suite_failures} tests failed")


@strategy("argued:docs")
def the_changelog_and_api_docs_are_current() -> Outcome:
    """[strategy] The changelog and API docs are current

    It is supported by the claim that the code is tested alone, and runs only once that
    claim holds: it has nothing more to judge. In `argued` alone, that claim is an
    unbound sub-conclusion, which produces nothing. Once unified, it is bound to the
    step of `checked`, which produces `code_tested`, a variable this library could not
    know: validation warns that the strategy ignores it (JP013).
    """
    return Pass()
