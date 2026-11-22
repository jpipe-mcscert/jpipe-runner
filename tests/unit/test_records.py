"""How a value's type is named in the report (``records.type_name``)."""

import sys
import types
from pathlib import Path

import pytest

from jpipe_runner.records import snapshot, type_name


def _defined_in(module: str, name: str = "Thing") -> type:
    return type(name, (), {"__module__": module, "__qualname__": name})


def test_a_builtin_type_is_named_alone() -> None:
    assert type_name(int) == "int"


def test_a_path_is_named_by_pathlib_on_every_version() -> None:
    # Python 3.13 defines it in pathlib._local.
    assert type_name(type(Path())) in ("pathlib.PosixPath", "pathlib.WindowsPath")


def test_a_type_defined_in_a_private_module_is_named_by_the_public_one_that_exports_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thing = _defined_in("kit._impl._local")
    monkeypatch.setitem(sys.modules, "kit", types.SimpleNamespace(Thing=thing))
    monkeypatch.setitem(sys.modules, "kit._impl", types.SimpleNamespace(Thing=thing))

    assert type_name(thing) == "kit.Thing"


def test_a_nested_type_is_looked_up_through_its_qualified_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outer = type("Outer", (), {"__module__": "kit._impl"})
    inner = type("Inner", (), {"__module__": "kit._impl", "__qualname__": "Outer.Inner"})
    outer.Inner = inner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "kit", types.SimpleNamespace(Outer=outer))

    assert type_name(inner) == "kit.Outer.Inner"


def test_a_private_module_is_kept_when_its_parent_does_not_export_the_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thing = _defined_in("kit._impl")
    monkeypatch.setitem(sys.modules, "kit", types.SimpleNamespace(Thing=object))

    assert type_name(thing) == "kit._impl.Thing"


def test_a_public_module_is_kept_even_when_its_parent_exports_the_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thing = _defined_in("kit.impl")
    monkeypatch.setitem(sys.modules, "kit", types.SimpleNamespace(Thing=thing))

    assert type_name(thing) == "kit.impl.Thing"


def test_naming_a_type_runs_none_of_its_package_s_code(monkeypatch: pytest.MonkeyPatch) -> None:
    kit = types.ModuleType("kit")

    def lazy(name: str) -> object:
        raise ImportError(f"lazy {name}")

    kit.__getattr__ = lazy  # type: ignore[method-assign]
    monkeypatch.setitem(sys.modules, "kit", kit)

    class Locked:
        __module__ = "kit._impl"
        __qualname__ = "Locked"

        def __deepcopy__(self, memo: object) -> object:
            raise TypeError("cannot copy")

    assert type_name(Locked) == "kit._impl.Locked"
    assert snapshot(Locked(), Path()).type == "kit._impl.Locked"  # type: ignore[attr-defined]
