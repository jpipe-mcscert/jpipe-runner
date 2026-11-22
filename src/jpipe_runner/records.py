"""Records: how a value the run saw is kept for its report, as it was at that moment.

A step receives the values themselves: what an evidence observed, what a supporter
produced. The report records them as they were when the run saw them, so that a step that
changes a value afterwards changes nothing the report or the run's events say (#184).
``snapshot`` takes a deep copy; a value that cannot be copied, such as a lock or an open
file, is recorded as an ``Uncopied``: its ``repr`` and its type, taken then.

A ``repr`` is canonical, the same on every run: Python's own, except that a path under the
run's root is shown relative to it, the items of a set are sorted, and an object's address
is left out, at any depth. The report writes a value that is not JSON with it.
"""

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jpipe_runner.diagnostics import shown_path

_REPR_LIMIT = 1000
"""The longest ``repr`` recorded for a value, in characters."""

_ADDRESS = re.compile(r" at 0x[0-9A-Fa-f]+")
"""The address in an object's default repr, ``<steps.Report object at 0x10f3a2b50>``."""

_RECURSION: dict[type, str] = {
    list: "[...]",
    dict: "{...}",
    tuple: "(...)",
    set: "{...}",
    frozenset: "{...}",
}


@dataclass(frozen=True, repr=False)
class Uncopied:
    """A value that could not be copied, recorded as it was when the run saw it. Its
    ``repr`` is the one the value had then, so that what shows a value shows it."""

    repr: str
    """Its canonical ``repr``, then."""
    type: str
    """Its type's qualified name."""

    def __repr__(self) -> str:
        return self.repr


def snapshot(value: Any, root: Path) -> Any:
    """``value`` as it is now, for the report: a deep copy, or, if it cannot be copied, an
    ``Uncopied`` holding its canonical ``repr`` (paths shown relative to ``root``) and its
    type."""
    try:
        return copy.deepcopy(value)
    # deepcopy raises whatever the value's __deepcopy__ or __reduce__ does, even SystemExit.
    except (Exception, SystemExit):  # NOSONAR
        return Uncopied(canonical_repr(value, root), type_name(type(value)))


def canonical_repr(value: Any, root: Path) -> str:
    """The canonical ``repr`` of ``value``, with paths shown relative to ``root``, cut at
    ``_REPR_LIMIT`` characters."""
    text = _Canonical(root)(value)
    if len(text) > _REPR_LIMIT:
        return text[: _REPR_LIMIT - 1] + "…"
    return text


def type_name(kind: type) -> str:
    """``kind``'s qualified name, without ``builtins.``."""
    if kind.__module__ == "builtins":
        return kind.__qualname__
    return f"{kind.__module__}.{kind.__qualname__}"


class _Canonical:
    """The canonical ``repr`` of a value, in the value and in the lists, tuples, sets and
    dicts it holds."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._seen: set[int] = set()

    def __call__(self, value: Any) -> str:
        kind = type(value)
        if isinstance(value, Path):
            return repr(kind(shown_path(str(value), self._root)))
        if kind not in _RECURSION:
            return _ADDRESS.sub("", _repr(value))
        if id(value) in self._seen:
            return _RECURSION[kind]
        self._seen.add(id(value))
        try:
            return self._container(value)
        finally:
            self._seen.discard(id(value))

    def _container(self, value: Any) -> str:
        if isinstance(value, dict):
            return "{" + ", ".join(f"{self(k)}: {self(v)}" for k, v in value.items()) + "}"
        items = [self(item) for item in value]
        if isinstance(value, list):
            return "[" + ", ".join(items) + "]"
        if isinstance(value, tuple):
            return "(" + ", ".join(items) + ("," if len(items) == 1 else "") + ")"
        name = type(value).__name__
        if not items:
            return f"{name}()"
        body = "{" + ", ".join(sorted(items)) + "}"
        return body if name == "set" else f"{name}({body})"


def _repr(value: Any) -> str:
    try:
        return repr(value)
    # A broken __repr__ must not break the report, nor end the run, even with SystemExit;
    # KeyboardInterrupt still stops it.
    except (Exception, SystemExit) as error:  # NOSONAR
        return f"<{type_name(type(value))} object: repr() raised {type(error).__name__}>"
