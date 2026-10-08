"""Static checks on the e2e scenarios, which run before the CLI exists to execute them."""

import ast
import importlib.util
import json
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType

import pytest

from jpipe_runner import loader
from jpipe_runner.steps import StepRegistry
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


def test_every_planned_scenario_exists() -> None:
    assert {scenario.name for scenario in SCENARIOS} == EXPECTED_SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.name)
def test_justification_loads(scenario: Scenario) -> None:
    # Every scenario's model is valid, cycles included: they are a validation error (#119),
    # not a load error.
    justification = loader.load(scenario.justification)
    model = json.loads(scenario.justification.read_text(encoding="utf-8"))
    assert len(justification) == len(model["elements"])


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


@contextmanager
def _imported(scenario: Scenario) -> Iterator[list[ModuleType]]:
    """The scenario's step libraries, imported as the runner will, then forgotten."""
    saved_path, saved_modules = list(sys.path), set(sys.modules)
    sys.path[:0] = [str(scenario.directory / entry) for entry in scenario.python_path]
    try:
        modules = []
        for index, library in enumerate(_libraries(scenario)):
            name = f"_scenario_{scenario.name}_{index}"
            spec = importlib.util.spec_from_file_location(name, library)
            assert spec is not None, library
            assert spec.loader is not None, library
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules.append(module)
        yield modules
    finally:
        sys.path[:] = saved_path
        for name in set(sys.modules) - saved_modules:
            del sys.modules[name]


def _libraries(scenario: Scenario) -> list[Path]:
    return sorted(
        {path for pattern in scenario.libraries for path in scenario.directory.glob(pattern)}
    )


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
    with _imported(scenario) as modules:
        registry = StepRegistry.from_modules(modules)
    declared = [name for library in _libraries(scenario) for name in _decorated_functions(library)]
    assert [step.function.__name__ for step in registry] == declared
