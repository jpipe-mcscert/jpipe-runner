"""Steps written against the standalone `checked` model of dominance.jd.

In `checked`, "The code is tested" is an evidence, `checked:tests`. The model `argued`
argues the same claim as a sub-conclusion, so the composition unified the two by their
label into the sub-conclusion `release:unified_0`, which keeps both old ids as aliases.
`checked:tests` still binds through its alias `release:checked:tests`, and its step,
declared as evidence, runs as a cross-check after the argument below it (JP008, a
warning).
"""

from pathlib import Path
from xml.etree import ElementTree

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy


@evidence("checked:tests", observes={"report": "mock/junit.xml"}, produces=["code_tested"])
def the_code_is_tested(report: Path) -> Outcome:
    """[evidence] The code is tested"""
    suite = ElementTree.parse(report).getroot()
    tests = int(suite.get("tests", "0"))
    if tests > 0:
        return Pass(code_tested=True)
    return Fail(f"{report} records no test")


@strategy("checked:gates", consumes=["code_tested"])
def all_release_gates_pass(code_tested: bool) -> Outcome:
    """[strategy] All release gates pass"""
    if code_tested:
        return Pass()
    return Fail("the code is not tested")
