"""Importing step libraries: module names, sys.path, sys.modules, and JP020/JP021 (#120)."""

import sys
from pathlib import Path

import pytest

from jpipe_runner.diagnostics import Severity
from jpipe_runner.libraries import (
    LIBRARY_IMPORT_FAILED,
    UNUSABLE_LIBRARY_NAME,
    LibraryLoadError,
    imported,
)
from jpipe_runner.steps import StepRegistry

STEP = """\
from pathlib import Path
from jpipe_runner import Pass, evidence

@evidence("m:e", observes={"log": "log.txt"}, produces=["ok"])
def checked(log: Path):
    return Pass(ok=True)
"""


def _write(directory: Path, name: str, source: str) -> Path:
    file = directory / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(source, encoding="utf-8")
    return file


def _codes(error: pytest.ExceptionInfo[LibraryLoadError]) -> list[str]:
    return [diagnostic.code for diagnostic in error.value.diagnostics]


def test_a_library_is_a_module_named_after_its_file_while_the_run_lasts(tmp_path: Path) -> None:
    library = _write(tmp_path, "release_steps.py", STEP)

    with imported([library]) as modules:
        assert [module.__name__ for module in modules] == ["release_steps"]
        assert sys.modules["release_steps"] is modules[0]
        registry = StepRegistry.from_modules(modules)
        assert registry.steps[0].name == "release_steps.checked"

    assert "release_steps" not in sys.modules


def test_libraries_are_imported_in_order_and_once(tmp_path: Path) -> None:
    b = _write(tmp_path, "b.py", "")
    a = _write(tmp_path, "a.py", "")

    with imported([b, a, b]) as modules:
        assert [module.__name__ for module in modules] == ["b", "a"]


def test_a_library_can_define_a_dataclass(tmp_path: Path) -> None:
    source = "from dataclasses import dataclass\n\n@dataclass\nclass Point:\n    x: int\n"
    library = _write(tmp_path, "shapes.py", source)

    with imported([library]) as (module,):
        assert module.Point(1).x == 1


def test_the_python_path_comes_first_while_the_run_lasts(tmp_path: Path) -> None:
    library = _write(tmp_path, "lib/steps.py", "")
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    saved = sys.path
    before = list(sys.path)

    with imported([library], python_path=[helpers]):
        assert sys.path[0] == str(helpers.resolve())

    assert sys.path is saved
    assert sys.path == before


def test_sys_path_is_restored_exactly_after_an_exception_and_a_step_that_changed_it(
    tmp_path: Path,
) -> None:
    library = _write(tmp_path, "steps.py", "")
    before = list(sys.path)

    with pytest.raises(RuntimeError):
        _run_a_step_that_changes_sys_path_and_fails(library, tmp_path)

    assert sys.path == before


def _run_a_step_that_changes_sys_path_and_fails(library: Path, python_path: Path) -> None:
    with imported([library], python_path=[python_path]):
        sys.path.append("/somewhere/a/step/added")
        sys.path.remove(str(python_path.resolve()))
        raise RuntimeError("a step failed")


def test_helpers_imported_from_the_python_path_are_forgotten_after_the_run(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "root_helper.py", "NUMBER = 1\n")
    _write(tmp_path, "pkg/sub.py", "NUMBER = 2\n")
    _write(tmp_path, "late_helper.py", "NUMBER = 3\n")
    source = "from root_helper import NUMBER\nfrom pkg.sub import NUMBER as OTHER\n"
    library = _write(tmp_path, "pkg/math_steps.py", source)

    with imported([library], python_path=[tmp_path]):
        import late_helper  # type: ignore[import-not-found]  # noqa: F401

        assert {"root_helper", "pkg", "pkg.sub", "late_helper"} <= sys.modules.keys()

    assert not {"root_helper", "pkg", "pkg.sub", "late_helper", "math_steps"} & set(sys.modules)


def test_modules_imported_from_elsewhere_stay_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    site = tmp_path / "site"
    _write(site, "installed_package.py", "")
    monkeypatch.syspath_prepend(str(site))
    library = _write(tmp_path / "lib", "steps.py", "import installed_package\n")

    with imported([library], python_path=[tmp_path / "lib"]):
        pass

    assert "installed_package" in sys.modules
    monkeypatch.delitem(sys.modules, "installed_package")


def test_a_missing_library_is_a_file_not_found_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError), imported([tmp_path / "missing.py"]):
        pass


def test_a_python_path_that_is_not_a_directory_is_refused(tmp_path: Path) -> None:
    library = _write(tmp_path, "steps.py", "")

    with pytest.raises(NotADirectoryError), imported([library], python_path=[library]):
        pass


@pytest.mark.parametrize(
    ("names", "sources"),
    [
        pytest.param(["a/steps.py", "b/steps.py"], ["", ""], id="two libraries, one name"),
        pytest.param(["json.py"], [""], id="an imported module's name"),
        pytest.param(["my-steps.py"], [""], id="not an identifier"),
    ],
)
def test_a_library_that_cannot_have_its_file_name_is_jp021_and_nothing_is_imported(
    tmp_path: Path, names: list[str], sources: list[str]
) -> None:
    marker = tmp_path / "imported"
    libraries = [
        _write(tmp_path, name, f"open({str(marker)!r}, 'w').close()\n{source}")
        for name, source in zip(names, sources, strict=True)
    ]

    with pytest.raises(LibraryLoadError) as error, imported(libraries):
        pass

    assert _codes(error) == [UNUSABLE_LIBRARY_NAME]
    assert error.value.diagnostics[0].severity is Severity.ERROR
    assert not marker.exists()


def test_a_name_found_on_the_python_path_is_jp021(tmp_path: Path) -> None:
    _write(tmp_path, "helpers/steps.py", "")
    library = _write(tmp_path, "lib/steps.py", "")

    with (
        pytest.raises(LibraryLoadError) as error,
        imported([library], python_path=[tmp_path / "helpers"]),
    ):
        pass

    assert _codes(error) == [UNUSABLE_LIBRARY_NAME]


def test_the_library_itself_on_the_python_path_is_no_conflict(tmp_path: Path) -> None:
    library = _write(tmp_path, "steps.py", "")

    with imported([library], python_path=[tmp_path]) as (module,):
        assert module.__name__ == "steps"


@pytest.mark.parametrize(
    ("source", "exception"),
    [
        pytest.param("import no_such_module_anywhere\n", "ModuleNotFoundError", id="import"),
        pytest.param("def broken(:\n", "SyntaxError", id="syntax"),
        pytest.param("x = undefined_name\n", "NameError", id="name"),
        pytest.param("import sys\nsys.exit(2)\n", "SystemExit", id="exit"),
        pytest.param(
            "from jpipe_runner import evidence\n\n@evidence()\ndef f():\n    pass\n",
            "TypeError",
            id="a declaration mistake",
        ),
    ],
)
def test_a_library_that_raises_on_import_is_jp020_at_its_line(
    tmp_path: Path, source: str, exception: str
) -> None:
    library = _write(tmp_path, "failing_steps.py", source)

    with pytest.raises(LibraryLoadError) as error, imported([library]):
        pass

    (diagnostic,) = error.value.diagnostics
    assert (diagnostic.code, diagnostic.severity) == (LIBRARY_IMPORT_FAILED, Severity.ERROR)
    assert exception in diagnostic.message
    assert str(library) in diagnostic.message
    assert "failing_steps" not in sys.modules


def test_the_traceback_of_a_failed_import_starts_in_the_library(tmp_path: Path) -> None:
    source = "from jpipe_runner import evidence\n\n@evidence()\ndef f():\n    pass\n"
    library = _write(tmp_path, "declared.py", source)

    with pytest.raises(LibraryLoadError) as error, imported([library]):
        pass

    trace = error.value.tracebacks[str(library)]
    assert [frame.filename for frame in trace.stack] == [str(library.resolve())]
    assert trace.exc_type is TypeError


def test_every_library_is_tried_and_every_failure_reported(tmp_path: Path) -> None:
    first = _write(tmp_path, "first.py", "import no_such_module_anywhere\n")
    fine = _write(tmp_path, "fine.py", "")
    second = _write(tmp_path, "second.py", "1 / 0\n")

    with pytest.raises(LibraryLoadError) as error, imported([first, fine, second]):
        pass

    assert _codes(error) == [LIBRARY_IMPORT_FAILED, LIBRARY_IMPORT_FAILED]
    assert error.value.diagnostics[0].fix is not None
    assert list(error.value.tracebacks) == [str(first), str(second)]
    assert "fine" not in sys.modules


def test_an_interrupt_is_not_a_failed_import(tmp_path: Path) -> None:
    library = _write(tmp_path, "interrupted.py", "raise KeyboardInterrupt\n")

    with pytest.raises(KeyboardInterrupt), imported([library]):
        pass


def test_a_failure_in_a_helper_is_located_in_the_helper(tmp_path: Path) -> None:
    helper = _write(tmp_path, "helpers/broken_helper.py", "VALUE = 1 / 0\n")
    library = _write(tmp_path, "uses_helper.py", "import broken_helper\n")

    with (
        pytest.raises(LibraryLoadError) as error,
        imported([library], python_path=[tmp_path / "helpers"]),
    ):
        pass

    assert f"at {helper.resolve()}, line 1" in error.value.diagnostics[0].message


def test_a_file_that_is_not_python_source_is_jp020(tmp_path: Path) -> None:
    library = _write(tmp_path, "steps.txt", "")

    with pytest.raises(LibraryLoadError) as error, imported([library]):
        pass

    assert _codes(error) == [LIBRARY_IMPORT_FAILED]


def test_a_library_another_one_imported_first_is_not_run_twice(tmp_path: Path) -> None:
    runs = tmp_path / "runs.txt"
    record = f"with open({str(runs)!r}, 'a') as log:\n    log.write('once\\n')\n"
    first = _write(tmp_path, "first_steps.py", "from second_steps import checked\n")
    second = _write(tmp_path, "second_steps.py", record + STEP)

    with imported([first, second], python_path=[tmp_path]) as modules:
        assert modules[1] is sys.modules["second_steps"]
        assert len(StepRegistry.from_modules(modules)) == 1

    assert runs.read_text(encoding="utf-8") == "once\n"
    assert "second_steps" not in sys.modules


def test_a_namespace_package_from_the_python_path_is_forgotten(tmp_path: Path) -> None:
    (tmp_path / "helpers" / "namespace_only").mkdir(parents=True)
    library = _write(tmp_path, "steps.py", "import namespace_only\n")

    with imported([library], python_path=[tmp_path / "helpers"]):
        assert "namespace_only" in sys.modules

    assert "namespace_only" not in sys.modules
