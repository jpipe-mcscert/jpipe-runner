"""Steps: the functions of a step library, declared by one decorator per kind (ADR-0006).

``@evidence``, ``@strategy``, ``@sub_conclusion`` and ``@conclusion`` declare a function as
the step implementing the elements whose ids they are given, and the variables it consumes
and produces. The kind is the decorator, so its signature allows only what that kind can
do: evidence observes artifacts of the world (``observes``) and consumes nothing, a
conclusion is terminal and produces nothing.

A decorator registers nothing. It attaches a ``Step`` to the function and returns the
function unchanged, so a step stays a plain function that a test can call. A
``StepRegistry`` collects the steps of a library's modules when a run needs them, so there
is no process-wide state for two runs to share (ADR-0009).

Mistakes visible in the declaration alone are a ``TypeError`` when the module is imported:
no id, a variable or parameter name that is not a Python identifier, an absolute path, a
parameter that is neither consumed nor observed, or a consumed variable or observed
artifact that is not a parameter. Whether the ids designate elements, and the
variables flow, depends on the model, and is checked against it (#115, #119).
"""

import inspect
import keyword
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import PurePosixPath, PureWindowsPath
from types import ModuleType
from typing import Any, TypeVar

from jpipe_runner.model import Kind
from jpipe_runner.outcomes import Outcome

StepFunction = TypeVar("StepFunction", bound=Callable[..., Outcome])

_STEP = "__jpipe_step__"
"""The attribute under which a decorated function carries its ``Step``."""

_KEYWORD_ARGUMENT = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)

_WILDCARDS = frozenset("*?[")


@dataclass(frozen=True)
class Artifact:
    """An artifact an evidence observes: a file, or a glob of files (ADR-0018, ADR-0019).

    ``path`` is relative to the run's working directory. The runner passes the artifact to
    the step's parameter ``name``: a ``Path``, or the sorted ``list[Path]`` a glob matches.
    """

    name: str
    path: str

    @property
    def is_glob(self) -> bool:
        """Whether ``path`` is a pattern, which may match several files."""
        return not _WILDCARDS.isdisjoint(self.path)


@dataclass(frozen=True)
class Step:
    """A function of a step library, as its decorator declares it. It holds no values."""

    kind: Kind
    ids: tuple[str, ...]
    """The ids it was given, in order. Binding resolves them to elements (#115)."""
    function: Callable[..., Outcome]
    consumes: tuple[str, ...] = ()
    """The variables it consumes, passed to the function as keyword arguments."""
    produces: tuple[str, ...] = ()
    """The variables it produces, returned in ``Pass``."""
    observes: tuple[Artifact, ...] = ()
    """The artifacts it observes, passed to the function by name. Only evidence observes."""

    @property
    def name(self) -> str:
        """The function's qualified name, as reports show it: ``module.function``."""
        return f"{self.function.__module__}.{self.function.__qualname__}"


def evidence(
    *ids: str, observes: Mapping[str, str] | None = None, produces: Iterable[str] = ()
) -> Callable[[StepFunction], StepFunction]:
    """Declare the step for the evidence ``ids``. Evidence observes the world: ``observes``
    maps each of the function's parameters to the artifact passed to it, a path relative to
    the run's working directory. It consumes nothing, and produces what it observed."""
    artifacts = _artifacts(Kind.EVIDENCE, {} if observes is None else observes)
    return _declare(Kind.EVIDENCE, ids, consumes=(), produces=produces, observes=artifacts)


def strategy(
    *ids: str, consumes: Iterable[str] = (), produces: Iterable[str] = ()
) -> Callable[[StepFunction], StepFunction]:
    """Declare the step for the strategy ``ids``."""
    return _declare(Kind.STRATEGY, ids, consumes=consumes, produces=produces)


def sub_conclusion(
    *ids: str, consumes: Iterable[str] = (), produces: Iterable[str] = ()
) -> Callable[[StepFunction], StepFunction]:
    """Declare a step checking the sub-conclusion ``ids``. Optional: an unbound
    sub-conclusion derives its status from what supports it."""
    return _declare(Kind.SUB_CONCLUSION, ids, consumes=consumes, produces=produces)


def conclusion(*ids: str, consumes: Iterable[str] = ()) -> Callable[[StepFunction], StepFunction]:
    """Declare a step checking the conclusion ``ids``. Optional: an unbound conclusion
    derives its status from what supports it. A conclusion is terminal: it produces nothing."""
    return _declare(Kind.CONCLUSION, ids, consumes=consumes, produces=())


def step_of(candidate: object) -> Step | None:
    """The step ``candidate`` was declared as, or ``None`` if it is not a step.

    A function that wraps a step with ``functools.wraps``, such as a logging decorator
    stacked above ``@evidence``, carries the declaration it copied. It is the step, so the
    run calls the wrapper the module exposes, not the function inside it.
    """
    if not inspect.isfunction(candidate):
        return None
    step = getattr(candidate, _STEP, None)
    if not isinstance(step, Step):
        return None
    return step if step.function is candidate else replace(step, function=candidate)


class StepRegistry:
    """The steps of a step library: what each declares, never a value (ADR-0009).

    Built for a run, from the library's modules, so nothing outlives it. A step is listed
    once however many modules expose it, in the order its modules and their namespaces
    list it.
    """

    def __init__(self, steps: Iterable[Step]) -> None:
        self._steps = tuple(dict.fromkeys(steps))

    @classmethod
    def from_modules(cls, modules: Iterable[ModuleType]) -> "StepRegistry":
        """The steps defined in, or imported into, the namespaces of ``modules``."""
        found = (step_of(value) for module in modules for value in vars(module).values())
        return cls(step for step in found if step is not None)

    @property
    def steps(self) -> tuple[Step, ...]:
        return self._steps

    def __iter__(self) -> Iterator[Step]:
        return iter(self._steps)

    def __len__(self) -> int:
        return len(self._steps)

    def __repr__(self) -> str:
        return f"StepRegistry({len(self._steps)} steps)"


def _declare(
    kind: Kind,
    ids: tuple[str, ...],
    *,
    consumes: Iterable[str],
    produces: Iterable[str],
    observes: tuple[Artifact, ...] = (),
) -> Callable[[StepFunction], StepFunction]:
    decorator = _decorator(kind)
    if len(ids) == 1 and callable(ids[0]):
        raise TypeError(
            f'{decorator} takes the ids of the elements it implements: {decorator}("id")'
        )
    if not ids:
        raise TypeError(f'{decorator}() needs the id of at least one element: {decorator}("id")')
    for element_id in ids:
        if not isinstance(element_id, str) or not element_id.strip():
            raise TypeError(
                f"{decorator}() takes element ids as non-empty strings, not {element_id!r}"
            )
    _no_repeats(decorator, "id", ids)
    consumed = _variables(decorator, "consumes", consumes)
    produced = _variables(decorator, "produces", produces)

    def declare(function: StepFunction) -> StepFunction:
        if not inspect.isfunction(function):
            raise TypeError(f"{decorator} declares a function, not {function!r}")
        if (existing := step_of(function)) is not None:
            raise TypeError(
                f"{function.__qualname__} is already declared as {existing.kind} "
                f"{existing.ids}: one function is one step"
            )
        _check_signature(decorator, function, consumed, observes)
        setattr(function, _STEP, Step(kind, ids, function, consumed, produced, observes))
        return function

    return declare


def _decorator(kind: Kind) -> str:
    return f"@{kind.value.replace('-', '_')}"


def _artifacts(kind: Kind, observes: Mapping[str, str]) -> tuple[Artifact, ...]:
    decorator = _decorator(kind)
    example = "observes={'changelog': 'CHANGELOG.md'}"
    if not isinstance(observes, Mapping):
        raise TypeError(
            f"{decorator}(observes=...) maps each parameter to the path it receives: {example}"
        )
    artifacts = []
    for name, path in observes.items():
        if not _is_name(name):
            raise TypeError(
                f"{decorator}(observes=...) takes parameter names that are Python "
                f"identifiers, not {name!r}"
            )
        if not isinstance(path, str) or not path.strip():
            raise TypeError(
                f"{decorator}(observes=...) takes paths as non-empty strings: {example}"
            )
        _check_path(decorator, path)
        artifacts.append(Artifact(name, path))
    return tuple(artifacts)


def _check_path(decorator: str, path: str) -> None:
    """``path`` names files relative to the run's working directory, by name or by glob."""
    if PurePosixPath(path).is_absolute() or PureWindowsPath(path).anchor:
        raise TypeError(
            f"{decorator}(observes=...) takes paths relative to the run's working "
            f"directory, so that the library works on every machine, not {path!r}"
        )
    if path.endswith(("/", "\\")):
        raise TypeError(
            f"{decorator}(observes=...) takes files, and {path!r} names a directory. "
            f"Observe the files it holds, with a glob such as {path + '**/*'!r}."
        )
    if any("**" in part and part != "**" for part in path.replace("\\", "/").split("/")):
        raise TypeError(
            f"{decorator}(observes=...): '**' matches any depth only as a whole part of a "
            f"path, as in 'build/**/*.xml', not {path!r}"
        )


def _is_name(name: object) -> bool:
    return isinstance(name, str) and name.isidentifier() and not keyword.iskeyword(name)


def _variables(decorator: str, argument: str, names: Iterable[str]) -> tuple[str, ...]:
    if isinstance(names, str):
        raise TypeError(
            f"{decorator}({argument}=...) takes a list of names: {argument}=[{names!r}]"
        )
    variables = tuple(names)
    for name in variables:
        if not _is_name(name):
            raise TypeError(
                f"{decorator}({argument}=...) takes variable names that are Python "
                f"identifiers, not {name!r}"
            )
    _no_repeats(decorator, argument, variables)
    return variables


def _no_repeats(decorator: str, what: str, values: tuple[str, ...]) -> None:
    if repeated := sorted({value for value in values if values.count(value) > 1}):
        raise TypeError(f"{decorator}() is given the {what} {', '.join(map(repr, repeated))} twice")


def _check_signature(
    decorator: str,
    function: Callable[..., Any],
    consumed: tuple[str, ...],
    observed: tuple[Artifact, ...],
) -> None:
    """The function takes each consumed variable and observed artifact as a keyword
    argument, and needs no other."""
    parameters = inspect.signature(function).parameters.values()
    by_keyword = {p.name for p in parameters if p.kind in _KEYWORD_ARGUMENT}
    takes_any_keyword = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters)
    required = {
        p.name
        for p in parameters
        if p.default is inspect.Parameter.empty
        and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }
    # Evidence consumes nothing and other kinds observe nothing: a step's parameters are
    # one or the other.
    if decorator == _decorator(Kind.EVIDENCE):
        verb, passed, declaration = "observes", [a.name for a in observed], "observes={...}"
    else:
        verb, passed, declaration = "consumes", list(consumed), "consumes=[...]"
    problems = []
    if missing := [name for name in passed if name not in by_keyword and not takes_any_keyword]:
        problems.append(f"it {verb} {missing} but has no parameter for them")
    if unfed := sorted(required - set(passed)):
        problems.append(f"its parameters {unfed} are not {verb[:-1]}d, so nothing would pass them")
    if problems:
        raise TypeError(
            f"{decorator} {function.__qualname__}: {'; and '.join(problems)}. A step's "
            f"parameters are what it {verb}, as declared by {declaration}."
        )
