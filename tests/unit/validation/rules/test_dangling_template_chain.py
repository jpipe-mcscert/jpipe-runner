"""JP026 `DanglingTemplateChain`: the template chain names only elements of the model
(#177)."""

from jpipe_runner.diagnostics import Severity
from jpipe_runner.model import Justification, Placeholder, Relation, Template, TemplateChain
from jpipe_runner.rules import DanglingTemplateChain
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    STRATEGY,
    context,
    element,
    reported,
    step,
)

ELEMENTS = (element("m:c", CONCLUSION), element("m:s", STRATEGY), element("m:e", EVIDENCE))
RELATIONS = (Relation("m:e", "m:s"), Relation("m:s", "m:c"))
STEPS = (
    step(EVIDENCE, "m:e", observes={"log": "build/tests.log"}, produces=["ok"]),
    step(STRATEGY, "m:s", consumes=["ok"]),
)
WARNING = Severity.WARNING


def _with(chain: TemplateChain) -> Justification:
    return Justification("m", ELEMENTS, RELATIONS, chain)


def test_each_unknown_id_in_the_chain_is_a_warning() -> None:
    placeholder = Placeholder("m:e", "e", ("m:y",))
    chain = TemplateChain(("m:x",), (Template("t", ("m:c", "m:s", "m:e"), (placeholder,)),))

    assert reported(DanglingTemplateChain(), context(_with(chain), *STEPS)) == [
        ("JP026", WARNING, None),
        ("JP026", WARNING, None),
    ]


def test_a_chain_that_names_only_elements_is_not_reported() -> None:
    chain = TemplateChain(("m:e",), (Template("t", ("m:c", "m:s", "m:e")),))

    assert reported(DanglingTemplateChain(), context(_with(chain), *STEPS)) == []


def test_a_model_without_a_chain_is_not_reported() -> None:
    model = Justification("m", ELEMENTS, RELATIONS)

    assert reported(DanglingTemplateChain(), context(model, *STEPS)) == []
