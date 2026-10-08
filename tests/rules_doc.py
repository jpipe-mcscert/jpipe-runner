"""``docs/rules.md``, generated from the rules (#128, ADR-0010).

The page is the reference of every diagnostic code. Validation rules are rendered from
their classes: code, name, severity and summary in the table, then each docstring. The
codes reported outside validation, when a model is loaded or a step returns, are listed
below from the constants that define them. ``poetry run pytest --update-goldens``
rewrites the page; ``tests/unit/test_rules_doc.py`` fails when it is out of date.
"""

import inspect
from pathlib import Path

from jpipe_runner import artifacts, libraries, loader, model, outcomes
from jpipe_runner.validation import Rule, RuleSet
from tests.conftest import REPO_ROOT

PAGE = REPO_ROOT / "docs" / "rules.md"
UPDATE_HINT = "poetry run pytest --update-goldens"

# The codes reported outside validation: (code, name, when, summary).
OTHER_CODES = (
    (
        loader.SCHEMA_CONFORMANCE,
        "SchemaConformance",
        "loading the model",
        "The file is not UTF-8 JSON in the compiler's format, or is a template.",
    ),
    (
        model.DUPLICATE_ID,
        "UniqueElementId",
        "loading the model",
        "An id or alias designates several elements.",
    ),
    (
        model.DANGLING_RELATION,
        "RelationEndpointsExist",
        "loading the model",
        "A relation names an element that does not exist.",
    ),
    (
        model.CYCLE,
        "Acyclic",
        "loading the model",
        "The relations form a cycle: an element supports itself, directly or not.",
    ),
    (
        libraries.LIBRARY_IMPORT_FAILED,
        "LibraryImportFailed",
        "importing the step libraries",
        "A step library raised an exception when it was imported: nothing is validated or run.",
    ),
    (
        libraries.UNUSABLE_LIBRARY_NAME,
        "UnusableLibraryName",
        "importing the step libraries",
        "A library's file name cannot be its module's name: another library or module has "
        "it, or it is not a Python identifier.",
    ),
    (
        outcomes.NOT_AN_OUTCOME,
        "NotAnOutcome",
        "running a step",
        "A step returned something other than `Pass`, `Fail` or `Skip`.",
    ),
    (
        artifacts.UNREACHABLE_ARTIFACT,
        "UnreachableArtifact",
        "calling an evidence",
        "An artifact the evidence observes is missing, unreadable or a directory, or a glob "
        "matches no file: the step is not called.",
    ),
)

_INTRODUCTION = f"""\
# Diagnostic codes

<!-- Generated from src/jpipe_runner/rules.py by `{UPDATE_HINT}`. Do not edit. -->

Every problem the runner reports is a diagnostic with a code, `JPnnn`, which never changes
meaning. Its message is written for humans and may be reworded, so scripts and tests rely
on the code.

## Validation rules

Before running anything, the runner checks the step library against the model with the
rules below, and reports every problem it finds at once
([ADR-0010](adr/0010-diagnostics-as-data-rules-as-objects.md)).

- An **error** stops the run: no step executes.
- A **warning** is reported, and the run continues. A strict run counts warnings as errors.

No rule can be disabled.
"""


def render(rules: RuleSet) -> str:
    """The text of ``docs/rules.md`` for ``rules``."""
    parts = [_INTRODUCTION, _rule_table(rules), *map(_rule_section, rules), _other_codes()]
    return "\n".join(parts)


def _rule_table(rules: RuleSet) -> str:
    rows = [
        f"| [{rule.code}](#{_anchor(rule)}) | `{rule.name}` | {rule.severity} | {rule.summary} |"
        for rule in rules
    ]
    return "\n".join(["| Code | Rule | Severity | Reports |", "|---|---|---|---|", *rows, ""])


def _rule_section(rule: Rule) -> str:
    explanation = inspect.cleandoc(type(rule).__doc__ or "")
    return f"### {rule.code} `{rule.name}`\n\nSeverity: **{rule.severity}**.\n\n{explanation}\n"


def _anchor(rule: Rule) -> str:
    return f"{rule.code}-{rule.name}".lower()


def _other_codes() -> str:
    rows = [
        f"| {code} | `{name}` | {when} | {summary} |"
        for code, name, when, summary in sorted(OTHER_CODES)
    ]
    return "\n".join(
        [
            "## Codes reported outside validation",
            "",
            "These are errors. A model or a step library that cannot be loaded is not validated.",
            "While the steps run, an error fails the element it is about, and the run goes on:",
            "what that element supports is skipped.",
            "",
            "| Code | Name | Reported when | Reports |",
            "|---|---|---|---|",
            *rows,
            "",
        ]
    )


def write(page: Path, rules: RuleSet) -> None:
    page.write_text(render(rules), encoding="utf-8")
