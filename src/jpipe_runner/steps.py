"""Steps: the functions of a step library, declared by one decorator per kind (ADR-0006).

``@evidence``, ``@strategy``, ``@sub_conclusion`` and ``@conclusion`` declare a function as
the step implementing the elements whose ids they are given, and the variables it consumes
and produces. The kind is the decorator, so its signature allows only what that kind can
do: evidence observes artifacts of the world (``observes``) and consumes nothing, a
conclusion is terminal and produces nothing. What can be observed is an ``Observable``
(ADR-0028); a path is relative to the file that declares the step.

A step consumes a variable from the one step among its supporters that produces it
(ADR-0031). ``consumes`` lists the variables, each passed to the parameter of its name, or
maps each parameter to its source: a variable, or ``Produced(variable, by=id)`` to name
the part of the argument the value comes from, when several supporters produce it.

A decorator registers nothing. It attaches a ``Step`` to the function and returns the
function unchanged, so a step stays a plain function that a test can call. A
``StepRegistry`` collects the steps of a library's modules when a run needs them, so there
is no process-wide state for two runs to share (ADR-0009).

Mistakes visible in the declaration alone are a ``TypeError`` when the module is imported:
no id, a variable or parameter name that is not a Python identifier, an absolute path, a
parameter that is neither consumed nor observed, or a consumed variable or observed
artifact that is not a parameter. Whether the ids designate elements, and the
variables flow, depends on the model, and is checked against it (#115, #119). So is
whether the function reads what it is passed, from its bytecode (``Step.unread``,
ADR-0037), since a step that never reads an input is not a mistake its import can refuse.
"""

import dis
import inspect
import keyword
import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import CodeType, ModuleType
from typing import Any, NamedTuple, TypeVar

from jpipe_runner.model import Kind
from jpipe_runner.observables import File, Observable, checked_shape
from jpipe_runner.outcomes import Outcome

StepFunction = TypeVar("StepFunction", bound=Callable[..., Outcome])

_STEP = "__jpipe_step__"
"""The attribute under which a decorated function carries its ``Step``."""

_KEYWORD_ARGUMENT = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)


@dataclass(frozen=True)
class Artifact:
    """An artifact an evidence observes (ADR-0018): what is observed, and the step's
    parameter ``name`` that receives what the ``observable`` sights."""

    name: str
    observable: Observable


@dataclass(frozen=True)
class Produced:
    """The value of ``variable`` produced at or below the element ``by`` designates, for a
    step to consume when several of its supporters produce that variable (ADR-0031).

    ``by`` is an id as a step's decorator takes one (ADR-0007): it may designate the
    producer itself, or an element it supports, such as the conclusion of the sub-argument
    the value comes from.
    """

    variable: str
    by: str

    def __post_init__(self) -> None:
        if not _is_name(self.variable):
            raise TypeError(
                f"Produced() takes a variable name that is a Python identifier, not "
                f"{self.variable!r}"
            )
        if not isinstance(self.by, str) or not self.by.strip():
            raise TypeError(f"Produced(by=...) takes an element id, not {self.by!r}")


@dataclass(frozen=True)
class Input:
    """A parameter of a step, and the variable it receives (ADR-0031): from the one step
    among the step's supporters that produces it, at or below the element ``by``
    designates when it is given."""

    parameter: str
    variable: str
    by: str | None = None


@dataclass(frozen=True)
class Step:
    """A function of a step library, as its decorator declares it. It holds no values."""

    kind: Kind
    ids: tuple[str, ...]
    """The ids it was given, in order. Binding resolves them to elements (#115)."""
    function: Callable[..., Outcome]
    inputs: tuple[Input, ...] = ()
    """What it consumes: each parameter, and the variable it receives."""
    produces: tuple[str, ...] = ()
    """The variables it produces, returned in ``Pass``."""
    observes: tuple[Artifact, ...] = ()
    """The artifacts it observes, passed to the function by name. Only evidence observes."""
    directory: Path = Path()
    """The directory of the file that declares it: what the paths it observes are relative to."""

    @property
    def name(self) -> str:
        """The function's qualified name, as reports show it: ``module.function``."""
        return f"{self.function.__module__}.{self.function.__qualname__}"

    @property
    def consumes(self) -> tuple[str, ...]:
        """The variables it consumes, each once, in the order of its inputs."""
        return tuple(dict.fromkeys(each.variable for each in self.inputs))

    @property
    def passed(self) -> tuple[str, ...]:
        """The keyword arguments a run passes to the function: what an evidence observes,
        and what any other step consumes, each by its parameter's name."""
        if self.kind is Kind.EVIDENCE:
            return tuple(artifact.name for artifact in self.observes)
        return tuple(each.parameter for each in self.inputs)

    @property
    def unread(self) -> "Unread":
        """The ``passed`` parameters that the function never reads, and those it takes only
        through ``**kwargs``, which cannot be checked by name (ADR-0037).

        A parameter is read when an instruction of the function's code loads it, or a
        function nested in it does, or the function calls ``locals()``, ``vars()``,
        ``eval()`` or ``exec()``. That
        needs no source, so a function typed at a prompt or built by ``exec`` is checked
        too. The function is the one declared, under any ``functools.wraps`` wrapper, as
        ``inspect.signature`` sees it.
        """
        passed = self.passed
        code = _code(self.function) if passed else None
        if code is None:
            return Unread()
        named, read = _named(code), _read(code)
        return Unread(
            tuple(name for name in passed if name in named and name not in read),
            tuple(name for name in passed if name not in named),
        )


class Unread(NamedTuple):
    """What a step is passed and does not visibly read."""

    never: tuple[str, ...] = ()
    """Parameters the function never reads."""
    unnamed: tuple[str, ...] = ()
    """Inputs the function takes only through ``**kwargs``."""


_VARIABLES = frozenset(dis.haslocal) | frozenset(dis.hasfree)
"""The instructions on a local, cell or free variable, as this version of Python has them."""

_ACCESS = re.compile(r"(?:^|_)(LOAD|STORE|DELETE)_")
"""What an instruction does to each variable it names, in order: ``STORE_FAST_LOAD_FAST``
stores its first and loads its second."""

_EVERY_LOCAL = frozenset({"locals", "vars", "eval", "exec"})
"""The builtins that reach a function's local variables without loading them by name."""

_FRAME_LOCALS = "f_locals"
"""The attribute of a frame that holds its local variables, as ``sys._getframe()`` or
``inspect.currentframe()`` return it."""


def _code(function: Callable[..., Any]) -> CodeType | None:
    """The code of the function ``function`` declares, under its wrappers, if it has one."""
    declared = inspect.unwrap(function, stop=lambda f: hasattr(f, "__signature__"))
    code = getattr(declared, "__code__", None)
    return code if isinstance(code, CodeType) else None


def _named(code: CodeType) -> tuple[str, ...]:
    """The parameters ``code`` takes by keyword: neither positional-only ones, nor ``*args``
    nor ``**kwargs``. A keyword argument with the name of a positional-only parameter goes
    to ``**kwargs``."""
    return code.co_varnames[code.co_posonlyargcount : code.co_argcount + code.co_kwonlyargcount]


def _read(code: CodeType) -> frozenset[str]:
    """The local variables ``code`` reads: those it loads, and those a nested function
    reads (its cell variables); every one if it calls ``locals()``, ``vars()``, ``eval()``
    or ``exec()``, or reads a frame's ``f_locals``.

    An instruction on a variable that this does not know how to read, as a later version of
    Python may add, counts as a read of every variable it names: a missed warning is the
    safe way to be wrong. ``LOAD_FAST_AND_CLEAR`` saves the variable a comprehension is
    about to reuse, and is no read.
    """
    read = set(code.co_cellvars)
    for instruction in dis.get_instructions(code):
        name, value = instruction.opname, instruction.argval
        if (name in ("LOAD_GLOBAL", "LOAD_NAME") and value in _EVERY_LOCAL) or (
            name == "LOAD_ATTR" and value == _FRAME_LOCALS
        ):
            return frozenset(code.co_varnames)
        if instruction.opcode not in _VARIABLES or name == "LOAD_FAST_AND_CLEAR":
            continue
        names = value if isinstance(value, tuple) else (value,)
        accesses = _ACCESS.findall(name)
        if len(accesses) != len(names):
            read.update(names)
        else:
            read.update(n for n, access in zip(names, accesses, strict=True) if access == "LOAD")
    return frozenset(read)


def evidence(
    *ids: str,
    observes: Mapping[str, str | Observable] | None = None,
    produces: Iterable[str] = (),
) -> Callable[[StepFunction], StepFunction]:
    """Declare the step for the evidence ``ids``. Evidence observes the world: ``observes``
    maps each of the function's parameters to what is passed to it. A string is the path of
    a file, or a glob of files, relative to the file that declares the step; anything else
    is an ``Observable``. It consumes nothing, and produces what it observed."""
    artifacts = _artifacts(Kind.EVIDENCE, {} if observes is None else observes)
    return _declare(Kind.EVIDENCE, ids, consumes=(), produces=produces, observes=artifacts)


Consumes = Iterable[str] | Mapping[str, str | Produced]
"""What a step consumes: a list of variables, each passed to the parameter of its name, or
a map from each parameter to a variable or a ``Produced``."""


def strategy(
    *ids: str, consumes: Consumes = (), produces: Iterable[str] = ()
) -> Callable[[StepFunction], StepFunction]:
    """Declare the step for the strategy ``ids``."""
    return _declare(Kind.STRATEGY, ids, consumes=consumes, produces=produces)


def sub_conclusion(
    *ids: str, consumes: Consumes = (), produces: Iterable[str] = ()
) -> Callable[[StepFunction], StepFunction]:
    """Declare a step checking the sub-conclusion ``ids``. Optional: an unbound
    sub-conclusion derives its status from what supports it."""
    return _declare(Kind.SUB_CONCLUSION, ids, consumes=consumes, produces=produces)


def conclusion(*ids: str, consumes: Consumes = ()) -> Callable[[StepFunction], StepFunction]:
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
    consumes: Consumes,
    produces: Iterable[str],
    observes: tuple[Artifact, ...] = (),
) -> Callable[[StepFunction], StepFunction]:
    decorator = kind.decorator
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
    inputs = _inputs(decorator, consumes)
    produced = _variables(decorator, "produces", produces)

    def declare(function: StepFunction) -> StepFunction:
        if not inspect.isfunction(function):
            raise TypeError(f"{decorator} declares a function, not {function!r}")
        if (existing := step_of(function)) is not None:
            raise TypeError(
                f"{function.__qualname__} is already declared as {existing.kind} "
                f"{existing.ids}: one function is one step"
            )
        _check_signature(kind, function, inputs, observes)
        step = Step(kind, ids, function, inputs, produced, observes, _declared_in(function))
        setattr(function, _STEP, step)
        return function

    return declare


def _artifacts(kind: Kind, observes: Mapping[str, str | Observable]) -> tuple[Artifact, ...]:
    decorator = kind.decorator
    example = "observes={'changelog': 'CHANGELOG.md'}"
    if not isinstance(observes, Mapping):
        raise TypeError(
            f"{decorator}(observes=...) maps each parameter to what it receives: {example}"
        )
    artifacts = []
    for name, observed in observes.items():
        if not _is_name(name):
            raise TypeError(
                f"{decorator}(observes=...) takes parameter names that are Python "
                f"identifiers, not {name!r}"
            )
        # A bare string is a file, or a glob of files: File refuses what is not a path.
        observable = observed if isinstance(observed, Observable) else File(observed)
        try:
            hash(observable)
        except TypeError:
            raise TypeError(
                f"{decorator}(observes=...) takes observables that can be hashed, as a "
                f"frozen dataclass is, not {observable!r}"
            ) from None
        _check_shape(decorator, observable)
        artifacts.append(Artifact(name, observable))
    return tuple(artifacts)


def _check_shape(decorator: str, observable: Observable) -> None:
    """Refuse an observable the diagram cannot draw as it asks (``checked_shape``)."""
    try:
        checked_shape(observable)
    except ValueError as error:
        raise TypeError(f"{decorator}(observes=...) {error}") from None


def _declared_in(function: Callable[..., Any]) -> Path:
    """The directory of the file that defines ``function``: what its paths are relative
    to. A function defined nowhere, such as one typed at a prompt, is in the working
    directory."""
    filename = inspect.unwrap(function).__code__.co_filename
    return Path() if filename.startswith("<") else Path(filename).parent


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


def _inputs(decorator: str, consumes: Consumes) -> tuple[Input, ...]:
    """What a step consumes, from the list of its variables or the map of its parameters."""
    if not isinstance(consumes, Mapping):
        return tuple(Input(name, name) for name in _variables(decorator, "consumes", consumes))
    inputs = []
    for parameter, source in consumes.items():
        if not _is_name(parameter):
            raise TypeError(
                f"{decorator}(consumes=...) takes parameter names that are Python "
                f"identifiers, not {parameter!r}"
            )
        if isinstance(source, Produced):
            inputs.append(Input(parameter, source.variable, source.by))
        elif _is_name(source):
            inputs.append(Input(parameter, source))
        else:
            raise TypeError(
                f"{decorator}(consumes=...) maps each parameter to a variable name or a "
                f"Produced(variable, by=id), not {source!r}"
            )
    return tuple(inputs)


def _no_repeats(decorator: str, what: str, values: tuple[str, ...]) -> None:
    if repeated := sorted({value for value in values if values.count(value) > 1}):
        raise TypeError(f"{decorator}() is given the {what} {', '.join(map(repr, repeated))} twice")


def _check_signature(
    kind: Kind,
    function: Callable[..., Any],
    inputs: tuple[Input, ...],
    observed: tuple[Artifact, ...],
) -> None:
    """The function takes each input and observed artifact as a keyword argument, and needs
    no other."""
    decorator = kind.decorator
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
    if kind is Kind.EVIDENCE:
        verb, passed, declaration = "observes", [a.name for a in observed], "observes={...}"
    else:
        verb, passed, declaration = "consumes", [i.parameter for i in inputs], "consumes=[...]"
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
