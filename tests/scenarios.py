"""End-to-end scenarios: discovery and the ``scenario.toml`` format (see tests/README.md)."""

import importlib.util
import sys
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

SCENARIOS_ROOT = Path(__file__).parent / "e2e" / "scenarios"
SCENARIO_FILE = "scenario.toml"
JUSTIFICATION_FILE = "justification.json"
GOLDEN_FILE = "expected.json"

# The exit codes a scenario may expect (#124). 2 (usage) and 4 (I/O) are about how the
# runner is invoked, which a scenario fixes, so no scenario can legitimately expect them.
EXIT_CODES = {0: "ok", 1: "justification failed", 3: "validation failed"}

# The scenarios whose model the loader refuses, and the codes it refuses them with. Their
# libraries still import, but bind to nothing: there is no model to bind them to.
REFUSED_MODELS = {"circular_dependency": ["JP004"]}

_REQUIRED = {"description": str, "origin": str, "libraries": list, "exit_code": int}
_OPTIONAL = {"python_path": list, "exercises": list}


class ScenarioError(ValueError):
    """A scenario directory that does not follow the documented format."""


@dataclass(frozen=True)
class Scenario:
    name: str
    directory: Path
    description: str
    origin: str
    libraries: tuple[str, ...]
    python_path: tuple[str, ...]
    exit_code: int
    exercises: tuple[str, ...]

    @property
    def justification(self) -> Path:
        return self.directory / JUSTIFICATION_FILE

    @property
    def golden(self) -> Path:
        return self.directory / GOLDEN_FILE

    def library_files(self) -> list[Path]:
        """The step library files ``libraries`` names, each once, sorted."""
        return sorted({path for pattern in self.libraries for path in self.directory.glob(pattern)})

    @contextmanager
    def imported_libraries(self) -> Iterator[list[ModuleType]]:
        """The step libraries, imported with ``python_path`` on ``sys.path``, then forgotten.

        Unit tests use it to check libraries without the CLI. ``sys.path`` and
        ``sys.modules`` are restored on exit, so helpers the libraries import do not leak.
        """
        saved_path, saved_modules = list(sys.path), set(sys.modules)
        sys.path[:0] = [str(self.directory / entry) for entry in self.python_path]
        try:
            modules = []
            for index, library in enumerate(self.library_files()):
                name = f"_scenario_{self.name}_{index}"
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

    def command(self) -> list[str]:
        """The CLI invocation (#124), to run with the scenario's copy as working directory."""
        command = [sys.executable, "-m", "jpipe_runner", "--report", "json"]
        for library in self.libraries:
            command += ["--library", library]
        for path in self.python_path:
            command += ["--python-path", path]
        return [*command, JUSTIFICATION_FILE]


def load(directory: Path) -> Scenario:
    """Read and check ``directory/scenario.toml``."""
    where = directory / SCENARIO_FILE
    try:
        raw = tomllib.loads(where.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ScenarioError(f"{where}: {error}") from error

    unknown = raw.keys() - _REQUIRED.keys() - _OPTIONAL.keys()
    if unknown:
        raise ScenarioError(f"{where}: unknown keys {sorted(unknown)}")
    missing = _REQUIRED.keys() - raw.keys()
    if missing:
        raise ScenarioError(f"{where}: missing keys {sorted(missing)}")
    for key, expected_type in (_REQUIRED | _OPTIONAL).items():
        value: Any = raw.get(key, [])
        if not isinstance(value, expected_type) or isinstance(value, bool):
            raise ScenarioError(f"{where}: `{key}` must be a {expected_type.__name__}")
        if expected_type is list and not all(isinstance(item, str) for item in value):
            raise ScenarioError(f"{where}: `{key}` must be a list of strings")
    if raw["exit_code"] not in EXIT_CODES:
        raise ScenarioError(f"{where}: `exit_code` must be one of {sorted(EXIT_CODES)}")
    if not raw["libraries"]:
        raise ScenarioError(f"{where}: `libraries` must name at least one step library")

    scenario = Scenario(
        name=directory.name,
        directory=directory,
        description=raw["description"],
        origin=raw["origin"],
        libraries=tuple(raw["libraries"]),
        python_path=tuple(raw.get("python_path", [])),
        exit_code=raw["exit_code"],
        exercises=tuple(raw.get("exercises", [])),
    )
    if not scenario.justification.is_file():
        raise ScenarioError(f"{directory}: no {JUSTIFICATION_FILE}")
    for pattern in scenario.libraries:
        if not any(directory.glob(pattern)):
            raise ScenarioError(f"{where}: library `{pattern}` matches no file")
    for path in scenario.python_path:
        if not (directory / path).is_dir():
            raise ScenarioError(f"{where}: python_path `{path}` is not a directory")
    return scenario


def discover(root: Path = SCENARIOS_ROOT) -> list[Scenario]:
    """Every scenario under ``root``, sorted by name."""
    return [load(path.parent) for path in sorted(root.glob(f"*/{SCENARIO_FILE}"))]
