"""Values: what the steps of one run produce, and which element produced each (ADR-0009).

A ``ValueStore`` is created for a run and dropped with it, so two runs in one process share
nothing. It is the execution half of the split whose declaration half is the
``StepRegistry``: the registry says what a step consumes and produces, the store holds what
it did produce. ``UNSET`` stands for a variable nothing has produced, so a step that
legitimately produces ``None`` is not mistaken for one that produced nothing.

A value is held under its variable and the element whose step produced it, not under its
name alone: two steps may produce the same variable, and each consumer receives the value
of the one among its supporters (ADR-0031).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, Literal


class Unset(Enum):
    """The type of ``UNSET``, the value of a variable nothing has produced."""

    UNSET = "UNSET"

    def __repr__(self) -> str:
        return "UNSET"

    def __bool__(self) -> Literal[False]:
        return False


UNSET: Final = Unset.UNSET


@dataclass(frozen=True)
class ProducedValue:
    """A produced value, and the id of the element whose step produced it."""

    value: Any
    produced_by: str


class ValueStore:
    """The values produced during one run, each under its variable and its producer, in
    the order produced.

    An element's step produces a variable once. Producing it again is a ``ValueError``: a
    step runs once, and declares each variable it produces once, so a second write can
    only be a bug in the runner.
    """

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], ProducedValue] = {}

    def put(self, name: str, value: Any, produced_by: str) -> None:
        """Record that the step bound to the element ``produced_by`` produced ``name``."""
        if (produced_by, name) in self._values:
            raise ValueError(f"{name!r} is produced by {produced_by!r}, which already produced it")
        self._values[produced_by, name] = ProducedValue(value, produced_by)

    def get(self, name: str, produced_by: str) -> Any:
        """The value of ``name`` the element ``produced_by`` produced, or ``UNSET`` if it
        has not produced it."""
        entry = self._values.get((produced_by, name))
        return UNSET if entry is None else entry.value

    def producers(self, name: str) -> tuple[str, ...]:
        """The ids of the elements that produced ``name``, in the order they produced it."""
        return tuple(producer for producer, produced in self._values if produced == name)

    def entries(self) -> Iterator[tuple[str, ProducedValue]]:
        """Every produced value and its variable, in the order produced: a variable two
        elements produced appears twice, each time with its producer."""
        return ((name, value) for (_, name), value in self._values.items())

    def __contains__(self, name: object) -> bool:
        """Whether some element produced the variable ``name``."""
        return any(produced == name for _, produced in self._values)

    def __len__(self) -> int:
        """How many values were produced: one per variable and producer."""
        return len(self._values)

    def __repr__(self) -> str:
        return f"ValueStore({len(self._values)} values)"
