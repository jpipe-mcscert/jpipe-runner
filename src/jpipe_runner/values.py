"""Values: what the steps of one run produce, and which element produced each (ADR-0009).

A ``ValueStore`` is created for a run and dropped with it, so two runs in one process share
nothing. It is the execution half of the split whose declaration half is the
``StepRegistry``: the registry says what a step consumes and produces, the store holds what
it did produce. ``UNSET`` stands for a variable nothing has produced, so a step that
legitimately produces ``None`` is not mistaken for one that produced nothing.
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
    """The values produced during one run, by variable name, in the order produced.

    A variable is produced once. Producing it again is a ``ValueError``: two producers of
    one variable are rejected by validation before the run (#119), so a second write can
    only be a bug in the runner.
    """

    def __init__(self) -> None:
        self._values: dict[str, ProducedValue] = {}

    def put(self, name: str, value: Any, produced_by: str) -> None:
        """Record that the step bound to the element ``produced_by`` produced ``name``."""
        if (existing := self._values.get(name)) is not None:
            raise ValueError(
                f"{name!r} is produced by {produced_by!r}, "
                f"but {existing.produced_by!r} already produced it"
            )
        self._values[name] = ProducedValue(value, produced_by)

    def get(self, name: str) -> Any:
        """The value of ``name``, or ``UNSET`` if nothing has produced it."""
        entry = self._values.get(name)
        return UNSET if entry is None else entry.value

    def produced_by(self, name: str) -> str | None:
        """The id of the element that produced ``name``, or ``None`` if nothing has."""
        entry = self._values.get(name)
        return None if entry is None else entry.produced_by

    def entries(self) -> Iterator[tuple[str, ProducedValue]]:
        """Every produced variable and its value, in the order they were produced."""
        return iter(self._values.items())

    def __contains__(self, name: object) -> bool:
        return name in self._values

    def __len__(self) -> int:
        return len(self._values)

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __repr__(self) -> str:
        return f"ValueStore({len(self._values)} values)"
