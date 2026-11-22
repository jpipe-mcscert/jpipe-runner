"""How a value's type is named in the report (``records.type_name``)."""

import sys
import types
from pathlib import Path

import pytest

from jpipe_runner import records
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


def test_the_outermost_parent_that_exports_the_type_names_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thing = _defined_in("kit._impl._local")
    monkeypatch.setitem(sys.modules, "kit", types.SimpleNamespace(Thing=thing))
    monkeypatch.setitem(sys.modules, "kit._impl", types.SimpleNamespace())

    assert type_name(thing) == "kit.Thing"


def test_a_metaclass_hook_is_not_run_to_find_a_nested_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Hooked(type):
        def __getattribute__(cls, name: str) -> object:
            if name == "__dict__":
                raise RuntimeError("hooked")
            return super().__getattribute__(name)

    outer = Hooked("Outer", (), {"__module__": "kit._impl"})
    inner = type("Inner", (), {"__module__": "kit._impl", "__qualname__": "Outer.Inner"})
    type.__setattr__(outer, "Inner", inner)
    monkeypatch.setitem(sys.modules, "kit", types.SimpleNamespace(Outer=outer))

    assert type_name(inner) == "kit.Outer.Inner"


def test_a_lookup_that_raises_anyway_is_no_export(monkeypatch: pytest.MonkeyPatch) -> None:
    def raising(*_: object) -> object:
        raise RuntimeError("a library's object")

    thing = _defined_in("kit._impl")
    monkeypatch.setitem(sys.modules, "kit", types.SimpleNamespace(Thing=thing))
    monkeypatch.setattr(records.inspect, "getattr_static", raising)

    assert type_name(thing) == "kit._impl.Thing"


def test_a_nested_type_is_found_on_a_base_of_the_exported_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = type("Base", (), {"__module__": "kit._impl"})
    inner = type("Inner", (), {"__module__": "kit._impl", "__qualname__": "Outer.Inner"})
    base.Inner = inner  # type: ignore[attr-defined]
    outer = type("Outer", (base,), {"__module__": "kit._impl"})
    monkeypatch.setitem(sys.modules, "kit", types.SimpleNamespace(Outer=outer))

    assert type_name(inner) == "kit.Outer.Inner"


def test_a_class_without_the_nested_type_does_not_export_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outer = type("Outer", (), {"__module__": "kit._impl"})
    inner = type("Inner", (), {"__module__": "kit._impl", "__qualname__": "Outer.Inner"})
    monkeypatch.setitem(sys.modules, "kit", types.SimpleNamespace(Outer=outer))

    assert type_name(inner) == "kit._impl.Outer.Inner"
