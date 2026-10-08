"""Minimal in-memory validation contexts, for the rule tests (layer 1, tests/README.md).

A case builds a small model and a few steps, and asserts what one rule reports: codes,
severities and elements, never messages.
"""

from collections.abc import Iterable
from pathlib import Path

from jpipe_runner import loader
from jpipe_runner.diagnostics import Severity
from jpipe_runner.model import Element, Justification, Kind, Relation
from jpipe_runner.outcomes import Outcome, Pass
from jpipe_runner.steps import Step, StepRegistry
from jpipe_runner.validation import Rule, ValidationContext

Reported = tuple[str, Severity, str | None]

# Models composed by jPipe 2.5.0, kept verbatim: `jpipe process -i <name>.jd -m <model>
# -f JSON`. Refine is the `composed` scenario's; assemble.jd is jpipe-examples'
# release-example/assemble.jd; dominance.jd unifies an evidence with a sub-conclusion.
COMPOSED = {
    "refine": Path(__file__).parents[2] / "e2e" / "scenarios" / "composed" / "justification.json",
    "assemble": Path(__file__).parent / "fixtures" / "assemble.json",
    "dominance": Path(__file__).parent / "fixtures" / "dominance.json",
}

EVIDENCE, STRATEGY = Kind.EVIDENCE, Kind.STRATEGY
SUB_CONCLUSION, CONCLUSION = Kind.SUB_CONCLUSION, Kind.CONCLUSION


def element(element_id: str, kind: Kind, *aliases: str) -> Element:
    return Element(element_id, element_id, kind, aliases)


def model(*elements: Element, relations: Iterable[tuple[str, str]] = ()) -> Justification:
    """A model named ``m``. ``relations`` go from supporter to supported."""
    return Justification("m", elements, (Relation(s, t) for s, t in relations))


def composed(name: str) -> Justification:
    """One of the ``COMPOSED`` models."""
    return loader.load(COMPOSED[name])


def step(
    kind: Kind,
    *ids: str,
    consumes: Iterable[str] = (),
    produces: Iterable[str] = (),
    name: str = "f",
) -> Step:
    """A step as its decorator would declare it, without the decorator's checks."""

    def function(**_: object) -> Outcome:
        return Pass()

    function.__qualname__ = name
    return Step(kind, ids, function, tuple(consumes), tuple(produces))


def context(justification: Justification, *steps: Step) -> ValidationContext:
    return ValidationContext.of(justification, StepRegistry(steps))


def reported(rule: Rule, ctx: ValidationContext) -> list[Reported]:
    """What ``rule`` reports on ``ctx``, as (code, severity, element)."""
    return [(d.code, d.severity, d.element) for d in rule.check(ctx)]
