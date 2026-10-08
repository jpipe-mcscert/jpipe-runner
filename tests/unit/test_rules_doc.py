"""docs/rules.md is what the rules generate, and documents every code the package reports."""

import re

from jpipe_runner.rules import RULES
from tests.conftest import REPO_ROOT
from tests.rules_doc import OTHER_CODES, PAGE, UPDATE_HINT, render, write

PACKAGE = REPO_ROOT / "src" / "jpipe_runner"
_CODE = re.compile(r"""["'](JP\d{3})["']""")


def test_the_page_is_generated_from_the_rules(update_goldens: bool) -> None:
    if update_goldens:
        write(PAGE, RULES)
    assert PAGE.read_text(encoding="utf-8") == render(RULES), (
        f"{PAGE} is out of date: run `{UPDATE_HINT}` and review the diff"
    )


def test_every_code_the_package_defines_is_documented() -> None:
    defined = {code for path in PACKAGE.rglob("*.py") for code in _CODE.findall(path.read_text())}
    documented = {rule.code for rule in RULES} | {code for code, *_ in OTHER_CODES}
    assert defined <= documented


def test_no_code_is_both_a_rule_and_reported_elsewhere() -> None:
    assert not {rule.code for rule in RULES} & {code for code, *_ in OTHER_CODES}
