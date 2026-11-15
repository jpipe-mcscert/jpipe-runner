"""Artifacts: what an evidence observes, observed just before its step is called.

An evidence declares the artifacts it observes (ADR-0018), each an ``Observable``
(ADR-0028): a file, a glob of files, a value in a JSON file, an environment variable, or
one a step library defines. Before calling its step, the runner asks each one what it is
now. What it answers is recorded, and passed to the step.

An artifact that cannot be reached, a missing or unreadable file, a glob that matches
nothing, a variable that is not set, an observable that raises, is reported with ``JP019``,
and the step is not called: an observed artifact is never optional.
"""

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from jpipe_runner.diagnostics import Diagnostic, Severity
from jpipe_runner.observables import Context, Observation, Sighting, described
from jpipe_runner.steps import Artifact

UNREACHABLE_ARTIFACT = "JP019"

_BROKEN_FIX = "Correct the observable: observe() returns a Sighting, and raises nothing."


@dataclass(frozen=True)
class Observed:
    """The artifacts of one evidence, observed: what was recorded, what to pass to the step,
    and a ``JP019`` diagnostic for each artifact that could not be reached."""

    observations: tuple[Observation, ...]
    arguments: Mapping[str, Any]
    """What the step receives, by parameter name. Complete only when ``reachable``."""
    diagnostics: tuple[Diagnostic, ...]

    @property
    def reachable(self) -> bool:
        """Whether every artifact was reached, so that the step can be called."""
        return not self.diagnostics


def observe(artifacts: Iterable[Artifact], context: Context, element: str) -> Observed:
    """Observe ``artifacts``, declared by the evidence bound to ``element``, from ``context``."""
    observations: list[Observation] = []
    arguments: dict[str, Any] = {}
    diagnostics: list[Diagnostic] = []
    for artifact in artifacts:
        sighting = _sighted(artifact, context)
        arguments[artifact.name] = sighting.value
        observations.extend(sighting.observations)
        diagnostics.extend(_unreachable(artifact, sighting, element))
    return Observed(tuple(observations), MappingProxyType(arguments), tuple(diagnostics))


def _sighted(artifact: Artifact, context: Context) -> Sighting:
    """What ``artifact`` is now. An observable is code of the step library: one that
    raises, or answers anything but a sighting, could not be observed."""
    what = f"{type(artifact.observable).__name__}"
    declared = described(artifact.observable, context)
    try:
        sighting = artifact.observable.observe(context)
    except Exception as error:  # NOSONAR: whatever a library's observable raises
        problem = f"could not be observed: it raised {type(error).__name__}: {error}"
        return Sighting.unreachable(declared, f"a {what}", problem, _BROKEN_FIX)
    if not isinstance(sighting, Sighting):
        problem = f"could not be observed: it returned {type(sighting).__name__}, not a Sighting"
        return Sighting.unreachable(declared, declared, problem, _BROKEN_FIX)
    return sighting


def _unreachable(artifact: Artifact, sighting: Sighting, element: str) -> Iterator[Diagnostic]:
    for observation in sighting.observations:
        if (obstacle := observation.obstacle) is not None:
            yield Diagnostic(
                UNREACHABLE_ARTIFACT,
                Severity.ERROR,
                f"{obstacle.what}, observed as {artifact.name!r}, {obstacle.problem}",
                element=element,
                fix=obstacle.fix,
            )
