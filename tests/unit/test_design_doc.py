"""The diagrams in docs/design.md match the code.

The module diagram (a ``flowchart``) shows every module of ``src/jpipe_runner/``, and its
solid arrows (``-->``) are exactly the imports between them. Dotted arrows are data and
are not checked.

In the class diagram (a ``classDiagram``), each ``namespace`` stands for the module of the
same name, and lists exactly the module's public classes. Every module with a public class
has a namespace. Relationships and multiplicities are not checked.
"""

import ast
import re

import pytest

from tests.conftest import REPO_ROOT

DESIGN_DOC = REPO_ROOT / "docs" / "design.md"
PACKAGE = REPO_ROOT / "src" / "jpipe_runner"

_MERMAID = re.compile(r"^```mermaid\n(.*?)^```", re.MULTILINE | re.DOTALL)
_NAMESPACE = re.compile(r"namespace\s+(\w+)\s*\{$")
_CLASS = re.compile(r"class\s+(\w+)$")
_NODE = re.compile(r"(\w+)\s*[\[(]")
_EDGE = re.compile(r"(\w+)\s*(-->|-\.->)\s*(?:\|[^|]*\|\s*)?(\w+)$")

Edge = tuple[str, str]


def _diagram(markdown: str, kind: str) -> str:
    """The one Mermaid block of ``kind`` (``flowchart``, ``classDiagram``) in the page."""
    starts = re.compile(rf"^\s*{kind}\b", re.MULTILINE)
    blocks = [block for block in _MERMAID.findall(markdown) if starts.search(block)]
    assert len(blocks) == 1, f"expected one {kind} in {DESIGN_DOC}, found {len(blocks)}"
    return blocks[0]


def _module_diagram(markdown: str) -> tuple[set[str], set[Edge]]:
    """The flowchart's nodes, and its solid edges."""
    nodes: set[str] = set()
    imports: set[Edge] = set()
    for raw in _diagram(markdown, "flowchart").splitlines():
        line = raw.strip()
        if match := _EDGE.match(line):
            source, arrow, target = match.groups()
            nodes.update((source, target))
            if arrow == "-->":
                imports.add((source, target))
        elif match := _NODE.match(line):
            nodes.add(match.group(1))
    return nodes, imports


def _class_diagram(markdown: str) -> dict[str, set[str]]:
    """The classes declared in each namespace."""
    namespaces: dict[str, set[str]] = {}
    namespace: str | None = None
    for raw in _diagram(markdown, "classDiagram").splitlines():
        line = raw.strip()
        if namespace is not None and (match := _CLASS.match(line)):
            namespaces[namespace].add(match.group(1))
        elif namespace is not None and line == "}":
            namespace = None
        elif match := _NAMESPACE.match(line):
            namespace = match.group(1)
            namespaces.setdefault(namespace, set())
    return namespaces


def _modules() -> dict[str, ast.Module]:
    """The package's modules, by name, without ``__init__``."""
    return {
        path.stem: ast.parse(path.read_text(encoding="utf-8"))
        for path in sorted(PACKAGE.glob("*.py"))
        if path.stem != "__init__"
    }


def _imports(module: str, tree: ast.Module, modules: set[str]) -> set[Edge]:
    """The package modules that ``module`` imports. The package uses absolute imports only."""
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "jpipe_runner":
            imported.update(alias.name for alias in node.names)  # from jpipe_runner import x
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").removeprefix("jpipe_runner."))
        elif isinstance(node, ast.Import):
            imported.update(alias.name.removeprefix("jpipe_runner.") for alias in node.names)
    return {(module, target) for target in imported & modules if target != module}


def _classes(tree: ast.Module) -> set[str]:
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    }


MARKDOWN = DESIGN_DOC.read_text(encoding="utf-8")
MODULES = _modules()
NODES, IMPORT_EDGES = _module_diagram(MARKDOWN)
NAMESPACES = _class_diagram(MARKDOWN)


def test_module_diagram_shows_every_module() -> None:
    assert set(MODULES) - NODES == set()


def test_module_diagram_solid_arrows_are_the_imports() -> None:
    names = set(MODULES)
    expected = {edge for module, tree in MODULES.items() for edge in _imports(module, tree, names)}
    assert expected == IMPORT_EDGES


def test_class_diagram_has_a_namespace_per_module_with_classes() -> None:
    assert {module for module, tree in MODULES.items() if _classes(tree)} == set(NAMESPACES)


@pytest.mark.parametrize("namespace", sorted(NAMESPACES))
def test_namespace_lists_the_module_classes(namespace: str) -> None:
    assert namespace in MODULES, f"no module jpipe_runner.{namespace}"
    assert _classes(MODULES[namespace]) == NAMESPACES[namespace]
