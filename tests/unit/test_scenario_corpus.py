"""Static checks on the e2e scenarios, which run before the CLI exists to execute them."""

import ast
import json

import pytest

from tests.scenarios import Scenario, discover

SCENARIOS = discover()

# The v4 public API (#113, #114). A step library imports from `jpipe_runner` directly and
# nothing else from it: no v3 `framework` paths, no internals.
PUBLIC_API = {
    "evidence",
    "strategy",
    "sub_conclusion",
    "conclusion",
    "Outcome",
    "Pass",
    "Fail",
    "Skip",
}
EXPECTED_SCENARIOS = {
    # Ported from v3.6.0:tests/e2e/resources/.
    "simple_success",
    "complex_success",
    "skip_scenario",
    "alias_binding",
    "suffix_binding",
    "suffix_alias_binding",
    "simple_import",
    "circular_dependency",
    "missing_producer",
    "missing_consumer",
    "self_dependency",
    "exception_handling",
    # New in v4.
    "release_example",
    "composed",
}


def test_every_planned_scenario_exists() -> None:
    assert {scenario.name for scenario in SCENARIOS} == EXPECTED_SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_justification_has_the_compiler_shape(scenario: Scenario) -> None:
    model = json.loads(scenario.justification.read_text(encoding="utf-8"))
    assert {"name", "type", "elements", "relations"} <= model.keys()
    for element in model["elements"]:
        assert {"id", "label", "type"} <= element.keys()
    for relation in model["relations"]:
        assert relation.keys() == {"source", "target"}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_step_libraries_use_only_the_public_api(scenario: Scenario) -> None:
    libraries = sorted(
        {path for pattern in scenario.libraries for path in scenario.directory.glob(pattern)}
    )
    for library in libraries:
        tree = ast.parse(library.read_text(encoding="utf-8"), filename=str(library))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("jpipe_runner"):
                assert node.module == "jpipe_runner", f"{library}: imports from {node.module}"
                assert {alias.name for alias in node.names} <= PUBLIC_API, library
            if isinstance(node, ast.Import):
                assert not any(a.name.startswith("jpipe_runner") for a in node.names), library
