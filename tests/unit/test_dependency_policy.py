"""The runtime dependencies are tested ranges, declared alike everywhere (ADR-0026).

Each one is a ``>=floor,<cap`` range in pyproject.toml, and debian/control declares the
same floor, so that the Ubuntu package needs what the floor job tests.
"""

import re
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT
from tests.floors import RANGE, floors, runtime_dependencies

CONTROL = (REPO_ROOT / "debian" / "control").read_text(encoding="utf-8")


@pytest.mark.parametrize(("name", "spec"), sorted(runtime_dependencies().items()))
def test_each_runtime_dependency_is_a_range_with_a_floor_and_a_cap(name: str, spec: str) -> None:
    assert isinstance(spec, str), f"{name} = {spec!r}"
    assert RANGE.match(spec), f"{name} = {spec!r}"


@pytest.mark.parametrize(("name", "floor"), sorted(floors().items()))
def test_the_ubuntu_package_declares_the_same_floor(name: str, floor: str) -> None:
    declared = re.search(rf"python3-{re.escape(name)} \(>= (?P<floor>[^)]+)\)", CONTROL)

    assert declared is not None, f"debian/control does not declare a floor for {name}"
    assert declared["floor"] == floor


def test_an_exact_pin_is_not_a_range(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.poetry.dependencies]\npython = ">=3.11"\nnetworkx = "3.5"\n', encoding="utf-8"
    )

    with pytest.raises(ValueError, match=re.escape("networkx = '3.5' is not a '>=floor,<cap'")):
        floors(pyproject)
