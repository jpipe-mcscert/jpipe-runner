"""Libraries: importing a run's step libraries, and forgetting them after it (ADR-0020).

``imported`` is a context manager. Inside it, the libraries are imported, each as a module
named after its file (``steps.py`` is ``steps``), registered in ``sys.modules``, and the
``python_path`` entries are first on ``sys.path``: the steps run inside it, so that what
they import when called is found as it was when they were imported. On exit, ``sys.path``
is restored exactly, whatever happened, and the libraries are dropped from
``sys.modules``, with the modules imported from the ``python_path`` entries, so that two
runs in one process share nothing (ADR-0009).

A library that cannot be imported is never skipped, nor reported as a bare traceback
(v3, #75). Each problem becomes a diagnostic, and they are raised together in a
``LibraryLoadError``: ``JP021`` when a library's file name cannot be its module's name,
before anything is imported, then ``JP020`` for each library whose import raised.
"""

import importlib.util
import sys
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from os import PathLike
from pathlib import Path
from traceback import TracebackException
from types import MappingProxyType, ModuleType

from jpipe_runner.diagnostics import Diagnostic, Severity, user_traceback

LIBRARY_IMPORT_FAILED = "JP020"
UNUSABLE_LIBRARY_NAME = "JP021"

_RENAME = "Rename the library's file: its name, without '.py', is the name of its module."


class LibraryLoadError(Exception):
    """Step libraries that cannot be imported. It carries every problem, as diagnostics,
    and the traceback of each library whose import raised, by the path it was given as."""

    def __init__(
        self,
        diagnostics: Iterable[Diagnostic],
        tracebacks: Mapping[str, TracebackException] | None = None,
    ) -> None:
        self.diagnostics = tuple(diagnostics)
        self.tracebacks = MappingProxyType(dict(tracebacks or {}))
        super().__init__("\n".join(str(diagnostic) for diagnostic in self.diagnostics))


@contextmanager
def imported(
    libraries: Iterable[str | PathLike[str]], python_path: Iterable[str | PathLike[str]] = ()
) -> Iterator[tuple[ModuleType, ...]]:
    """The modules of ``libraries``, imported with ``python_path`` first on ``sys.path``.

    Raises ``FileNotFoundError`` if a library is not a file, ``NotADirectoryError`` if a
    ``python_path`` entry is not a directory, and ``LibraryLoadError`` if a library cannot
    be imported. A library given twice is imported once.
    """
    files = list(dict.fromkeys(Path(library) for library in libraries))
    for file in files:
        if not file.is_file():
            raise FileNotFoundError(f"no step library at {file}")
    entries = list(dict.fromkeys(Path(entry).resolve() for entry in python_path))
    for entry in entries:
        if not entry.is_dir():
            raise NotADirectoryError(f"the python path {entry} is not a directory")

    saved_path, saved_modules = list(sys.path), set(sys.modules)
    sys.path[:0] = [str(entry) for entry in entries]
    try:
        if problems := list(_unusable_names(files)):
            raise LibraryLoadError(problems)
        yield _import_all(files)
    finally:
        sys.path[:] = saved_path
        _forget(set(sys.modules) - saved_modules, {file.stem for file in files}, entries)


def _unusable_names(files: list[Path]) -> Iterator[Diagnostic]:
    """A diagnostic for each library that cannot be imported under its file's name."""
    by_name: dict[str, list[Path]] = {}
    for file in files:
        by_name.setdefault(file.stem, []).append(file)
    for name, same in by_name.items():
        if not name.isidentifier():
            yield _unusable(f"{same[0]}: {name!r} is not a Python identifier")
        elif len(same) > 1:
            paths = ", ".join(map(str, same))
            yield _unusable(f"{len(same)} libraries are named {name!r}: {paths}")
        elif (other := _other_module(name, same[0])) is not None:
            yield _unusable(f"{same[0]}: {name!r} is already the name of {other}")


def _other_module(name: str, file: Path) -> str | None:
    """What else ``name`` designates as a module, if anything but ``file``."""
    if name in sys.modules:
        return f"the module {sys.modules[name]!r}, already imported"
    spec = importlib.util.find_spec(name)
    if spec is None:
        return None
    if spec.origin is not None and Path(spec.origin).resolve() == file.resolve():
        return None
    return f"the module at {spec.origin or 'a package directory'}"


def _unusable(message: str) -> Diagnostic:
    return Diagnostic(UNUSABLE_LIBRARY_NAME, Severity.ERROR, message, fix=_RENAME)


def _import_all(files: list[Path]) -> tuple[ModuleType, ...]:
    """Import every library, in order. Raises ``LibraryLoadError`` if any raised."""
    modules: list[ModuleType] = []
    problems: list[Diagnostic] = []
    tracebacks: dict[str, TracebackException] = {}
    for file in files:
        try:
            modules.append(_import(file))
        except (Exception, SystemExit) as error:
            trace = user_traceback(error)
            tracebacks[str(file)] = trace
            problems.append(_import_failed(file, error, trace))
    if problems:
        raise LibraryLoadError(problems, tracebacks)
    return tuple(modules)


def _import(file: Path) -> ModuleType:
    name = file.stem
    spec = importlib.util.spec_from_file_location(name, file.resolve())
    if spec is None or spec.loader is None:
        raise ImportError(f"{file} cannot be imported as a Python module")
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs, as an import would: a library that defines a dataclass,
    # or imports itself, looks itself up in sys.modules.
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    return module


def _import_failed(file: Path, error: BaseException, trace: TracebackException) -> Diagnostic:
    # A SyntaxError names its file and line itself; anything else is located at the
    # deepest frame of the library's code, which is where the author can act.
    where = ""
    if trace.stack and not isinstance(error, SyntaxError):
        frame = trace.stack[-1]
        if Path(frame.filename) == file.resolve():
            where = f", at line {frame.lineno}"
        else:
            where = f", at {frame.filename}, line {frame.lineno}"
    fix = None
    if isinstance(error, ModuleNotFoundError):
        fix = "Install the module it imports, or pass the directory that holds it as a python path."
    return Diagnostic(
        LIBRARY_IMPORT_FAILED,
        Severity.ERROR,
        f"{file} cannot be imported: {type(error).__name__}: {error}{where}",
        fix=fix,
    )


def _forget(added: set[str], libraries: set[str], entries: list[Path]) -> None:
    """Drop from ``sys.modules`` the libraries, and the modules among ``added`` that were
    imported from a ``python_path`` entry. Other modules, such as third-party packages
    a step imported, stay cached: a C extension cannot be imported twice in a process."""
    tops = {name.partition(".")[0] for name in added if _from_entries(name, entries)}
    for name in added:
        if name in libraries or name.partition(".")[0] in tops:
            sys.modules.pop(name, None)


def _from_entries(name: str, entries: list[Path]) -> bool:
    """Whether the module ``name`` was found in one of ``entries``, as a top-level module
    or package of that entry."""
    file = getattr(sys.modules.get(name), "__file__", None)
    if not isinstance(file, str):
        return False
    path, top = Path(file).resolve(), name.partition(".")[0]
    return any(
        path.is_relative_to(entry) and path.relative_to(entry).parts[0].partition(".")[0] == top
        for entry in entries
    )
