"""The floor of each runtime dependency, as pyproject.toml declares it (ADR-0026).

``python -m tests.floors`` prints them as requirements, ``networkx==2.8.8``, one per line,
for the CI job that runs the suite on the oldest versions a supported channel installs.
"""

import re
import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

# `>=floor,<cap`, the only form ADR-0026 allows.
RANGE = re.compile(r"^>=\s*(?P<floor>[0-9][^,\s]*)\s*,\s*<\s*(?P<cap>[0-9][^,\s]*)$")


def runtime_dependencies(pyproject: Path = PYPROJECT) -> dict[str, str]:
    """Each runtime dependency, but Python, and its version constraint."""
    with pyproject.open("rb") as file:
        dependencies = tomllib.load(file)["tool"]["poetry"]["dependencies"]
    return {name: spec for name, spec in dependencies.items() if name != "python"}


def floors(pyproject: Path = PYPROJECT) -> dict[str, str]:
    """The floor of each runtime dependency. Raises ``ValueError`` for one that is not a
    ``>=floor,<cap`` range."""
    found = {}
    for name, spec in runtime_dependencies(pyproject).items():
        match = RANGE.match(spec) if isinstance(spec, str) else None
        if match is None:
            raise ValueError(f"{name} = {spec!r} is not a '>=floor,<cap' range (ADR-0026)")
        found[name] = match["floor"]
    return found


if __name__ == "__main__":
    sys.stdout.writelines(f"{name}=={floor}\n" for name, floor in floors().items())
