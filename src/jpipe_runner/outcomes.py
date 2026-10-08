"""Outcomes: what a step returns (ADR-0005).

A step reports its result by returning ``Pass``, ``Fail`` or ``Skip``. ``Pass`` carries the
values the step produces, so there is no ``produce`` callable to inject. v3 steps returned
a ``bool`` and produced values through a ``produce`` parameter. A step that returns
anything but an outcome is reported with ``JP017`` and told what to return instead.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from jpipe_runner.diagnostics import Diagnostic, Severity

NOT_AN_OUTCOME = "JP017"

_OUTCOMES = "Pass(), Fail(reason) or Skip(reason)"


@dataclass(frozen=True)
class Outcome:
    """What a step returns: ``Pass``, ``Fail`` or ``Skip``. Not instantiated itself."""

    def __new__(cls, *args: Any, **kwargs: Any) -> "Outcome":
        if cls is Outcome:
            raise TypeError(f"Outcome is not returned itself: return {_OUTCOMES}")
        return super().__new__(cls)


@dataclass(frozen=True, init=False, repr=False)
class Pass(Outcome):
    """The step's check holds. ``values`` are the variables it produces, by name.

    ``Pass()``, ``Pass({"coverage": 92.0})`` and ``Pass(coverage=92.0)`` all work, and can
    be combined. The mapping is positional-only, so any name can be passed as a keyword.
    """

    values: Mapping[str, Any]

    def __init__(self, values: Mapping[str, Any] | None = None, /, **kwargs: Any) -> None:
        if values is not None and not isinstance(values, Mapping):
            raise TypeError(
                f"Pass() takes a mapping of produced values, not {type(values).__name__}: "
                f"Pass({{'name': value}}) or Pass(name=value)"
            )
        produced = {} if values is None else dict(values)
        if not all(isinstance(name, str) for name in produced):
            raise TypeError(f"a produced variable is named by a str: {list(produced)!r}")
        if twice := sorted(produced.keys() & kwargs.keys()):
            raise TypeError(f"Pass() was given {twice!r} both in the mapping and as keywords")
        produced.update(kwargs)
        object.__setattr__(self, "values", MappingProxyType(produced))

    def __repr__(self) -> str:
        return f"Pass({dict(self.values)!r})" if self.values else "Pass()"


@dataclass(frozen=True)
class Fail(Outcome):
    """The step's check does not hold, for ``reason``."""

    reason: str

    def __post_init__(self) -> None:
        _check_reason(self)


@dataclass(frozen=True)
class Skip(Outcome):
    """The step declines to judge, for ``reason``. What it supports is skipped too."""

    reason: str = ""

    def __post_init__(self) -> None:
        _check_reason(self)


class NotAnOutcomeError(TypeError):
    """A step returned something that is not an outcome. ``diagnostic`` says what to do."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(str(diagnostic))


def as_outcome(returned: object, element_id: str) -> Outcome:
    """``returned``, the value a step bound to ``element_id`` returned, as an outcome.

    Raises ``NotAnOutcomeError`` (JP017) if it is not one. A ``bool`` is what a v3 step
    returned, so the fix names the outcome that replaces it.
    """
    if isinstance(returned, Outcome):
        return returned
    if returned is True:
        message, fix = "returned True", "Return Pass() instead of True."
    elif returned is False:
        message, fix = "returned False", "Return Fail(reason) instead of False."
    elif returned is None:
        message = "returned None"
        fix = f"Return {_OUTCOMES}. A function without a return statement returns None."
    elif isinstance(returned, Mapping):
        message = f"returned a {type(returned).__name__}"
        fix = "Return Pass(values) to produce these values."
    else:
        message, fix = f"returned a {type(returned).__name__}", f"Return {_OUTCOMES}."
    diagnostic = Diagnostic(
        NOT_AN_OUTCOME,
        Severity.ERROR,
        f"the step {message}, which is not an outcome",
        element=element_id,
        fix=fix,
    )
    raise NotAnOutcomeError(diagnostic)


def _check_reason(outcome: Fail | Skip) -> None:
    if not isinstance(outcome.reason, str):
        raise TypeError(
            f"{type(outcome).__name__}() takes a str reason, not {type(outcome.reason).__name__}"
        )
