"""Static checks on the e2e scenarios: what their golden reports cannot say.

The golden reports (tests/e2e/) pin what each run concludes. These check how the scenarios
are written: their libraries use the public API only, declare every decorated function and
observe files that exist, and a cross-check runs after the argument below it.
"""

import ast
import json
from pathlib import Path

import pytest

from jpipe_runner import loader
from jpipe_runner.engine import run
from jpipe_runner.libraries import LibraryLoadError
from jpipe_runner.model import InvalidJustificationError
from jpipe_runner.steps import StepRegistry
from tests.scenarios import REFUSED_LIBRARIES, REFUSED_MODELS, Scenario, discover

SCENARIOS = discover()
IMPORTABLE = [scenario for scenario in SCENARIOS if scenario.name not in REFUSED_LIBRARIES]

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
    "import_error",
    "unreachable_artifact",
    "assembled",
    "unified",
}


# The cross-checks of the composed scenarios: the element bound by a step written against
# a source model before composition, and the root of the argument below it, which runs
# first (ADR-0013, ADR-0021).
CROSS_CHECKS = {
    "composed": ("readiness:hook", "readiness:tested:testing"),
    "unified": ("release:unified_0", "release:argued:testing"),
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


@pytest.mark.parametrize(
    "scenario",
    [scenario for scenario in SCENARIOS if scenario.name in REFUSED_LIBRARIES],
    ids=lambda scenario: scenario.name,
)
def test_a_library_that_cannot_be_imported_is_reported(scenario: Scenario) -> None:
    with pytest.raises(LibraryLoadError) as error, scenario.imported_libraries():
        pass
    assert [d.code for d in error.value.diagnostics] == REFUSED_LIBRARIES[scenario.name]


@pytest.mark.parametrize("scenario", IMPORTABLE, ids=lambda scenario: scenario.name)
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
    [scenario for scenario in IMPORTABLE if scenario.exit_code == 0],
    ids=lambda scenario: scenario.name,
)
def test_every_observed_artifact_is_in_the_scenario(scenario: Scenario) -> None:
    # The runner fails an evidence whose artifact is unreachable (#144); in a scenario
    # meant to pass, every one is there, relative to the scenario's directory.
    with scenario.imported_libraries() as modules:
        registry = StepRegistry.from_modules(modules)
    for step in registry:
        for artifact in step.observes:
            found = list(scenario.directory.glob(artifact.path))
            assert found, f"{scenario.name}: {step.name} observes {artifact.path}, not found"


@pytest.mark.parametrize(
    "scenario",
    [scenario for scenario in SCENARIOS if scenario.name in CROSS_CHECKS],
    ids=lambda scenario: scenario.name,
)
def test_a_cross_check_runs_after_the_argument_below_it(scenario: Scenario) -> None:
    checked, argued = CROSS_CHECKS[scenario.name]
    justification = loader.load(scenario.justification)
    with scenario.imported_libraries() as modules:
        result = run(justification, StepRegistry.from_modules(modules), root=scenario.directory)
    order = [r.element.id for r in result]
    assert result.result(checked).ran
    assert result.result(checked).binding is not None
    assert result.result(checked).binding.step.kind == "evidence"
    assert order.index(argued) < order.index(checked)
