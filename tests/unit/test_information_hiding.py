"""NetworkX stays inside ``Justification`` (ADR-0016).

Only ``jpipe_runner.model`` imports NetworkX, and no public class, method, property or
function of the package mentions a NetworkX type in its signature.
"""

import ast
import importlib
import inspect
import typing
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from tests.conftest import REPO_ROOT

PACKAGE = REPO_ROOT / "src" / "jpipe_runner"
GRAPH_LIBRARY = "networkx"
GRAPH_OWNER = "model"


def _modules() -> list[str]:
    return sorted(path.stem for path in PACKAGE.glob("*.py") if path.stem != "__init__")


def _imports_the_graph_library(module: str) -> bool:
    tree = ast.parse((PACKAGE / f"{module}.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = (
            [alias.name for alias in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
            if isinstance(node, ast.ImportFrom)
            else []
        )
        if any(name.split(".")[0] == GRAPH_LIBRARY for name in names):
            return True
    return False


def _public_callables(module: str) -> Iterator[tuple[str, Callable[..., Any]]]:
    """Every public function, class constructor, method and property getter of ``module``."""
    namespace = importlib.import_module(f"jpipe_runner.{module}")
    for name, value in vars(namespace).items():
        if name.startswith("_") or getattr(value, "__module__", None) != namespace.__name__:
            continue
        if inspect.isfunction(value):
            yield name, value
        elif inspect.isclass(value):
            for member_name, member in vars(value).items():
                if member_name.startswith("_") and member_name != "__init__":
                    continue
                if isinstance(member, property) and member.fget is not None:
                    yield f"{name}.{member_name}", member.fget
                elif inspect.isfunction(member):
                    yield f"{name}.{member_name}", member


@pytest.mark.parametrize("module", _modules())
def test_only_the_model_imports_the_graph_library(module: str) -> None:
    assert _imports_the_graph_library(module) == (module == GRAPH_OWNER)


@pytest.mark.parametrize(
    ("qualname", "function"),
    [pytest.param(q, f, id=q) for module in _modules() for q, f in _public_callables(module)],
)
def test_no_public_signature_mentions_the_graph_library(
    qualname: str, function: Callable[..., Any]
) -> None:
    hints = typing.get_type_hints(function)
    leaks = {name: hint for name, hint in hints.items() if GRAPH_LIBRARY in repr(hint)}
    assert leaks == {}, f"{qualname} exposes {GRAPH_LIBRARY} types: {leaks}"
