"""Static checks on the e2e scenarios, which run before the CLI exists to execute them."""

import ast
import json
from pathlib import Path

import pytest

from jpipe_runner import loader
from jpipe_runner.model import InvalidJustificationError
from jpipe_runner.rules import RULES
from jpipe_runner.steps import StepRegistry
from jpipe_runner.validation import ValidationContext
from tests.scenarios import REFUSED_MODELS, Scenario, discover

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
DECORATORS = {"evidence", "strategy", "sub_conclusion", "conclusion"}
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


# What validation reports on each scenario, by code, until the golden reports pin it (#124).
# A scenario not listed reports nothing.
VALIDATION_CODES = {
    "composed": ["JP008"],
    "missing_consumer": ["JP011"],
    "missing_producer": ["JP009"],
    "self_dependency": ["JP014"],
}


def test_every_planned_scenario_exists() -> None:
    assert {scenario.name for scenario in SCENARIOS} == EXPECTED_SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_justification_loads(scenario: Scenario) -> None:
    if scenario.name in REFUSED_MODELS:
        with pytest.raises(InvalidJustificationError) as error:
            loader.load(scenario.justification)
        assert [d.code for d in error.value.diagnostics] == REFUSED_MODELS[scenario.name]
        return
    justification = loader.load(scenario.justification)
    model = json.loads(scenario.justification.read_text(encoding="utf-8"))
    assert len(justification) == len(model["elements"])


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_step_libraries_use_only_the_public_api(scenario: Scenario) -> None:
    for library in scenario.library_files():
        tree = ast.parse(library.read_text(encoding="utf-8"), filename=str(library))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("jpipe_runner"):
                assert node.module == "jpipe_runner", f"{library}: imports from {node.module}"
                assert {alias.name for alias in node.names} <= PUBLIC_API, library
            if isinstance(node, ast.Import):
                assert not any(a.name.startswith("jpipe_runner") for a in node.names), library


def _decorated_functions(library: Path) -> list[str]:
    tree = ast.parse(library.read_text(encoding="utf-8"), filename=str(library))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id in DECORATORS
            for d in node.decorator_list
        )
    ]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_step_libraries_declare_every_decorated_function(scenario: Scenario) -> None:
    # Validation scenarios (cycles, self-dependencies, missing producers) still import:
    # their faults are in the dataflow, which only the model can judge (#119).
    with scenario.imported_libraries() as modules:
        registry = StepRegistry.from_modules(modules)
    declared = [
        name for library in scenario.library_files() for name in _decorated_functions(library)
    ]
    assert [step.function.__name__ for step in registry] == declared


@pytest.mark.parametrize(
    "scenario",
    [scenario for scenario in SCENARIOS if scenario.name not in REFUSED_MODELS],
    ids=lambda scenario: scenario.name,
)
def test_validation_reports_what_the_scenario_is_about(scenario: Scenario) -> None:
    with scenario.imported_libraries() as modules:
        registry = StepRegistry.from_modules(modules)
    report = RULES.run(ValidationContext.of(loader.load(scenario.justification), registry))
    assert [d.code for d in report.diagnostics] == VALIDATION_CODES.get(scenario.name, [])
    assert report.passed is (scenario.exit_code != 3)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_every_observed_artifact_is_in_the_scenario(scenario: Scenario) -> None:
    # The runner fails an evidence whose artifact is unreachable (#144); in a scenario
    # meant to pass, every one is there, relative to the scenario's directory.
    with scenario.imported_libraries() as modules:
        registry = StepRegistry.from_modules(modules)
    for step in registry:
        for artifact in step.observes:
            found = list(scenario.directory.glob(artifact.path.rstrip("/")))
            assert found, f"{scenario.name}: {step.name} observes {artifact.path}, not found"
