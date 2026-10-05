import importlib
import importlib.metadata
import tomllib

import pytest

import jpipe_runner
from tests.conftest import REPO_ROOT


def test_version_matches_pyproject() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert jpipe_runner.__version__ == pyproject["tool"]["poetry"]["version"]


def test_version_falls_back_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_installed(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    with monkeypatch.context() as patch:
        patch.setattr(importlib.metadata, "version", not_installed)
        assert importlib.reload(jpipe_runner).__version__ == "0+unknown"
    importlib.reload(jpipe_runner)


def test_layer_marker_is_applied(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("unit") is not None
    assert request.node.get_closest_marker("e2e") is None
