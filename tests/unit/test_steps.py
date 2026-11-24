import builtins
import dis
import functools
import hashlib
import importlib
import inspect
import sys
import textwrap
import types
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import jpipe_runner
from jpipe_runner import Fail, Outcome, Pass, conclusion, evidence, strategy, sub_conclusion
from jpipe_runner.model import Kind
from jpipe_runner.observables import Context, Env, File, Observable, Sighting
from jpipe_runner.steps import Artifact, Input, Produced, Step, StepRegistry, Unread, step_of

HERE = Path(__file__).parent
SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
"""This file's SHA-256: the fingerprint of the steps it declares."""
"""Where the steps of these tests are declared: what their paths are relative to."""


def test_the_package_exports_the_authoring_api() -> None:
    assert set(jpipe_runner.__all__) == {
        "evidence",
        "strategy",
        "sub_conclusion",
        "conclusion",
        "Outcome",
        "Pass",
        "Produced",
        "Fail",
        "Skip",
        "Observable",
        "Context",
        "Sighting",
        "File",
        "JsonValue",
        "Env",
        "__version__",
    }


def test_a_decorator_returns_the_function_itself() -> None:
    def the_tests_pass() -> Outcome:
        return Pass(tests_pass=True)

    decorated = evidence("m:e")(the_tests_pass)
    assert decorated is the_tests_pass
    assert decorated() == Pass(tests_pass=True)


@pytest.mark.parametrize(
    ("decorator", "kind", "consumes", "produces"),
    [
        pytest.param(evidence("m:x", produces=["a"]), Kind.EVIDENCE, (), ("a",), id="evidence"),
        pytest.param(
            strategy("m:x", consumes=["a"], produces=["b"]),
            Kind.STRATEGY,
            ("a",),
            ("b",),
            id="strategy",
        ),
        pytest.param(
            sub_conclusion("m:x", consumes=["a"], produces=["b"]),
            Kind.SUB_CONCLUSION,
            ("a",),
            ("b",),
            id="sub_conclusion",
        ),
        pytest.param(
            conclusion("m:x", consumes=["a"]), Kind.CONCLUSION, ("a",), (), id="conclusion"
        ),
    ],
)
def test_the_decorator_is_the_kind(
    decorator: Callable[[Callable[..., Outcome]], Callable[..., Outcome]],
    kind: Kind,
    consumes: tuple[str, ...],
    produces: tuple[str, ...],
) -> None:
    def function(a: int = 0) -> Outcome:
        return Pass()

    inputs = tuple(Input(name, name) for name in consumes)
    assert step_of(decorator(function)) == Step(
        kind, ("m:x",), function, inputs, produces, directory=HERE
    )


def test_evidence_consumes_nothing_and_a_conclusion_produces_nothing() -> None:
    assert "consumes" not in inspect.signature(evidence).parameters
    assert "produces" not in inspect.signature(conclusion).parameters
    with pytest.raises(TypeError):
        evidence("m:e", consumes=["a"])  # type: ignore[call-arg]


def test_ids_are_positional_one_or_many() -> None:
    @evidence("rigor:r17:e_metric", "rigor:r18:e")
    def report_metrics() -> Outcome:
        return Pass()

    step = step_of(report_metrics)
    assert step is not None
    assert step.ids == ("rigor:r17:e_metric", "rigor:r18:e")


def test_variables_are_kept_in_the_order_given_from_any_iterable() -> None:
    @strategy("m:s", consumes=("b", "a"), produces=iter(["d", "c"]))
    def combine(a: int, b: int) -> Outcome:
        return Pass()

    step = step_of(combine)
    assert step is not None
    assert (step.consumes, step.produces) == (("b", "a"), ("d", "c"))


def test_consumes_maps_each_parameter_to_a_variable_or_a_named_producer() -> None:
    @strategy(
        "m:s",
        consumes={
            "tests": Produced("coverage", by="m:a"),
            "docs": Produced("coverage", by="m:b"),
            "release": "version",
        },
    )
    def gates(tests: float, docs: float, release: str) -> Outcome:
        return Pass()

    step = step_of(gates)
    assert step is not None
    assert step.inputs == (
        Input("tests", "coverage", "m:a"),
        Input("docs", "coverage", "m:b"),
        Input("release", "version"),
    )
    assert step.consumes == ("coverage", "version")


def test_a_list_of_variables_passes_each_to_the_parameter_of_its_name() -> None:
    @conclusion("m:c", consumes=["a", "b"])
    def holds(a: int, b: int) -> Outcome:
        return Pass()

    step = step_of(holds)
    assert step is not None
    assert step.inputs == (Input("a", "a"), Input("b", "b"))


def test_a_step_is_named_by_its_module_and_qualified_name() -> None:
    @conclusion("m:c")
    def holds() -> Outcome:
        return Pass()

    step = step_of(holds)
    assert step is not None
    assert (
        step.name
        == f"{__name__}.test_a_step_is_named_by_its_module_and_qualified_name.<locals>.holds"
    )


def test_a_step_may_consume_what_it_produces() -> None:
    # A self-dependency is a fact about the dataflow, reported by validation (#119).
    @strategy("m:s", consumes=["a"], produces=["a"])
    def loop(a: int) -> Outcome:
        return Pass(a=a)

    assert step_of(loop) is not None


@pytest.mark.parametrize(
    "declare",
    [
        pytest.param(lambda: evidence(), id="no id"),
        pytest.param(lambda: evidence(""), id="empty id"),
        pytest.param(lambda: evidence("  "), id="blank id"),
        pytest.param(lambda: evidence(1), id="int id"),
        pytest.param(lambda: evidence("m:e", "m:e"), id="id twice"),
        pytest.param(lambda: evidence("m:e", produces="a"), id="produces a string"),
        pytest.param(lambda: strategy("m:s", consumes="a"), id="consumes a string"),
        pytest.param(lambda: evidence("m:e", produces=["a-b"]), id="not an identifier"),
        pytest.param(lambda: evidence("m:e", produces=["class"]), id="a keyword"),
        pytest.param(lambda: evidence("m:e", produces=[1]), id="not a string"),
        pytest.param(lambda: strategy("m:s", consumes=["a", "a"]), id="variable twice"),
        pytest.param(lambda: strategy("m:s", consumes={"a-b": "a"}), id="parameter not a name"),
        pytest.param(lambda: strategy("m:s", consumes={"a": "a-b"}), id="source not a name"),
        pytest.param(lambda: strategy("m:s", consumes={"a": 1}), id="source not a string"),
        pytest.param(lambda: Produced("a-b", by="m:e"), id="produced not a name"),
        pytest.param(lambda: Produced("a", by=""), id="produced by an empty id"),
        pytest.param(lambda: Produced("a", by=1), id="produced by an int"),
    ],
)
def test_a_malformed_declaration_is_a_type_error(declare: Callable[[], object]) -> None:
    with pytest.raises(TypeError):
        declare()


def test_a_decorator_without_its_ids_is_a_type_error() -> None:
    def the_tests_pass() -> Outcome:
        return Pass()

    with pytest.raises(TypeError, match="ids"):
        evidence(the_tests_pass)  # type: ignore[arg-type]


def test_only_a_function_is_declared() -> None:
    declare = evidence("m:e")
    with pytest.raises(TypeError):
        declare(print)  # type: ignore[arg-type]


def test_a_function_is_one_step() -> None:
    @evidence("m:e")
    def the_tests_pass() -> Outcome:
        return Pass()

    declare = strategy("m:s")
    with pytest.raises(TypeError, match="already declared"):
        declare(the_tests_pass)


def _not_consumed(a: int) -> Outcome:
    return Pass()


def _positional_only(a: int, /) -> Outcome:
    return Pass()


def _no_parameters() -> Outcome:
    return Pass()


@pytest.mark.parametrize(
    ("function", "consumes"),
    [
        pytest.param(_not_consumed, [], id="a parameter that is not consumed"),
        pytest.param(_no_parameters, ["a"], id="a consumed variable that is not a parameter"),
        pytest.param(_positional_only, ["a"], id="a consumed variable passed only by position"),
    ],
)
def test_the_parameters_are_the_consumed_variables(
    function: Callable[..., Outcome], consumes: list[str]
) -> None:
    declare = strategy("m:s", consumes=consumes)
    with pytest.raises(TypeError, match="consume"):
        declare(function)


def test_the_parameters_are_the_keys_of_a_map_of_inputs() -> None:
    declare = strategy("m:s", consumes={"b": Produced("a", by="m:e")})
    with pytest.raises(TypeError, match=r"\['b'\]"):
        declare(_not_consumed)


def test_a_parameter_with_a_default_or_keywords_need_not_match() -> None:
    @strategy("m:s", consumes=["a", "b"])
    def takes_any(a: int, timeout: float = 1.0, **others: Any) -> Outcome:
        return Pass()

    @conclusion("m:c", consumes=["a"])
    def keyword_only(*, a: int) -> Outcome:
        return Pass() if a else Fail("no a")

    assert step_of(takes_any) is not None
    assert step_of(keyword_only) is not None


def test_evidence_observes_artifacts_passed_to_its_parameters_by_name() -> None:
    @evidence(
        "m:e",
        observes={"changelog": "CHANGELOG.md", "reports": "build/*.xml"},
        produces=["ok"],
    )
    def checked(changelog: Path, reports: list[Path]) -> Outcome:
        return Pass(ok=changelog.name == "CHANGELOG.md")

    step = step_of(checked)
    assert step is not None
    assert step.observes == (
        Artifact("changelog", File("CHANGELOG.md")),
        Artifact("reports", File("build/*.xml")),
    )
    assert step.directory == HERE
    assert checked(Path("CHANGELOG.md"), []) == Pass(ok=True)


@pytest.mark.parametrize(
    ("declared", "recorded"),
    [
        pytest.param("mock/../mock/junit.xml", "mock/junit.xml", id="'..' inside"),
        pytest.param("./CHANGELOG.md", "CHANGELOG.md", id="'.'"),
        pytest.param("build//reports/*.xml", "build/reports/*.xml", id="'//'"),
        pytest.param("../VERSION", "../VERSION", id="a leading '..'"),
        pytest.param("a/../build/**/./*.xml", "build/**/*.xml", id="a glob"),
    ],
)
def test_an_observed_path_is_recorded_as_a_changed_file_is_named(
    declared: str, recorded: str
) -> None:
    @evidence("m:e", observes={"a": declared})
    def observing(a: Path) -> Outcome:
        return Pass()

    step = step_of(observing)
    assert step is not None
    assert step.observes == (Artifact("a", File(recorded)),)
    assert File(declared).path == recorded


def test_a_step_observes_nothing_unless_declared() -> None:
    @evidence("m:e")
    def unobserved() -> Outcome:
        return Pass()

    @strategy("m:s")
    def judged() -> Outcome:
        return Pass()

    for function in (unobserved, judged):
        step = step_of(function)
        assert step is not None
        assert step.observes == ()


def test_evidence_observes_any_observable_and_a_string_is_a_file() -> None:
    @evidence("m:e", observes={"ci": Env("CI"), "log": "build/tests.log"})
    def observing(ci: str, log: Path) -> Outcome:
        return Pass()

    step = step_of(observing)
    assert step is not None
    assert step.observes == (Artifact("ci", Env("CI")), Artifact("log", File("build/tests.log")))


class _Drawn(Observable):
    """An observable that asks to be drawn as ``shape``, or raises it."""

    def __init__(self, shape: object) -> None:
        self._shape = shape

    def __hash__(self) -> int:
        return 0

    @property
    def shape(self) -> str:
        if isinstance(self._shape, Exception):
            raise self._shape
        return self._shape  # type: ignore[return-value]

    def describe(self, context: Context) -> str:
        return "drawn"

    def observe(self, context: Context) -> Sighting:
        return Sighting.of("drawn", None)


@pytest.mark.parametrize(
    ("shape", "message"),
    [
        pytest.param("note", r"cannot draw _Drawn as 'note': .* box3d, cds", id="an evidence's"),
        pytest.param("circle", "cannot draw _Drawn as 'circle'", id="grows with its label"),
        pytest.param(RuntimeError("no"), "its shape raised RuntimeError", id="raises"),
        pytest.param(["tab"], r"cannot draw _Drawn as \['tab'\]", id="not a string"),
    ],
)
def test_an_observable_the_diagram_cannot_draw_is_refused_at_import(
    shape: object, message: str
) -> None:
    with pytest.raises(TypeError, match=message):

        @evidence("m:e", observes={"a": _Drawn(shape)})
        def observing(a: object) -> Outcome:
            return Pass()


def test_an_observable_in_one_of_the_shapes_is_accepted() -> None:
    @evidence("m:e", observes={"a": _Drawn("cylinder")})
    def observing(a: object) -> Outcome:
        return Pass()

    assert step_of(observing) is not None


def test_a_step_typed_at_a_prompt_is_declared_in_the_working_directory() -> None:
    namespace: dict[str, Any] = {"evidence": evidence, "Pass": Pass}
    exec('@evidence("m:e", observes={"a": "a.txt"})\ndef typed(a): return Pass()', namespace)

    step = step_of(namespace["typed"])
    assert step is not None
    assert step.directory == Path()


class Unhashable(Observable):
    __hash__ = None  # type: ignore[assignment]

    def describe(self, context: Context) -> str:
        return "unhashable"

    def observe(self, context: Context) -> Sighting:
        return Sighting.of("unhashable", 1)


def test_only_evidence_observes() -> None:
    with pytest.raises(TypeError):
        strategy("m:s", observes={"a": "a.txt"})  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("observes", "problem"),
    [
        pytest.param("CHANGELOG.md", "maps each parameter", id="a string"),
        pytest.param(["CHANGELOG.md"], "maps each parameter", id="a list"),
        pytest.param({"a-b": "x"}, "identifiers", id="not an identifier"),
        pytest.param({"class": "x"}, "identifiers", id="a keyword"),
        pytest.param({1: "x"}, "identifiers", id="not a string name"),
        pytest.param({"a": ""}, "non-empty", id="empty path"),
        pytest.param({"a": 1}, "non-empty", id="not a string path"),
        pytest.param({"a": Unhashable()}, "hashed", id="an observable that cannot be hashed"),
        pytest.param({"a": "/etc/hosts"}, "relative", id="absolute"),
        pytest.param({"a": "C:\\reports\\x.xml"}, "relative", id="absolute on Windows"),
        pytest.param({"a": "\\\\server\\share\\x"}, "relative", id="a UNC path"),
        pytest.param({"a": "src/"}, "directory", id="a directory"),
        pytest.param({"a": "src\\"}, "directory", id="a directory on Windows"),
        pytest.param({"a": "build/*/"}, "directory", id="a glob of directories"),
        pytest.param({"a": "build/**.xml"}, "whole part", id="'**' inside a name"),
        pytest.param({"a": "a**/b.xml"}, "whole part", id="'**' ending a name"),
        pytest.param({"a": "build/*/../x.xml"}, "before the first wildcard", id="'..' in a glob"),
        pytest.param({"a": "mock/.."}, "directory", id="'..' to a directory"),
        pytest.param({"a": "."}, "directory", id="the working directory"),
    ],
)
def test_a_malformed_observation_is_a_type_error(observes: Any, problem: str) -> None:
    with pytest.raises(TypeError, match=problem):
        evidence("m:e", observes=observes)


def _observes_a(a: Path) -> Outcome:
    return Pass()


@pytest.mark.parametrize(
    ("function", "observes"),
    [
        pytest.param(_observes_a, {}, id="a parameter that is not observed"),
        pytest.param(_no_parameters, {"a": "a.txt"}, id="an artifact that is not a parameter"),
        pytest.param(_observes_a, {"b": "b.txt"}, id="another name"),
    ],
)
def test_the_parameters_of_evidence_are_its_observed_artifacts(
    function: Callable[..., Outcome], observes: dict[str, str]
) -> None:
    declare = evidence("m:e", observes=observes)
    with pytest.raises(TypeError, match="observe"):
        declare(function)


def test_a_wrapper_of_a_step_is_the_step() -> None:
    @evidence("m:e")
    def inner() -> Outcome:
        return Pass()

    @functools.wraps(inner)
    def logged() -> Outcome:
        return inner()

    assert step_of(logged) == Step(Kind.EVIDENCE, ("m:e",), logged, directory=HERE)


def _library(file: Path, namespace: dict[str, Any]) -> ModuleType:
    """The module of ``file``, executed with ``namespace``, as a library is imported."""
    module = ModuleType(file.stem)
    module.__file__ = str(file)
    module.__dict__.update(namespace)
    exec(compile(file.read_text(encoding="utf-8"), str(file), "exec"), module.__dict__)
    return module


_CHECK = "def check():\n    return Pass()\n"


@pytest.mark.parametrize(
    ("factory", "call"),
    [
        # The library applies the decorator to a function the factory defines.
        pytest.param(
            f"def make(threshold):\n    {_CHECK.replace(chr(10), chr(10) + '    ')}return check\n",
            "step = evidence('m:e')(make(0.8))\n",
            id="function-made-elsewhere",
        ),
        # The factory declares the step itself: only the library holds the threshold.
        pytest.param(
            "def make(threshold):\n"
            "    @evidence('m:e')\n"
            f"    {_CHECK.replace(chr(10), chr(10) + '    ')}return check\n",
            "step = make(0.8)\n",
            id="step-made-elsewhere",
        ),
    ],
)
def test_a_step_is_fingerprinted_with_the_library_that_exposes_it(
    tmp_path: Path, factory: str, call: str
) -> None:
    helpers, library = tmp_path / "helpers.py", tmp_path / "library.py"
    helpers.write_text(f"from jpipe_runner import Pass, evidence\n{factory}", encoding="utf-8")
    library.write_text(call, encoding="utf-8")
    made = _library(helpers, {})
    module = _library(library, {"evidence": evidence, "make": made.make})

    (step,) = StepRegistry.from_modules([module])

    # A new threshold in the library, or a new body in helpers, is a new fingerprint.
    both = library.read_bytes() + helpers.read_bytes()
    assert step.library_sha256 == hashlib.sha256(both).hexdigest()


def test_a_step_is_fingerprinted_with_its_wrappers(tmp_path: Path) -> None:
    helpers, library = tmp_path / "helpers.py", tmp_path / "library.py"
    helpers.write_text(
        "import functools\n"
        "def logged(function):\n"
        "    @functools.wraps(function)\n"
        "    def wrapper(*args, **kwargs):\n"
        "        return function(*args, **kwargs)\n"
        "    return wrapper\n",
        encoding="utf-8",
    )
    library.write_text(
        "@logged\n@evidence('m:e')\ndef check():\n    return Pass()\n", encoding="utf-8"
    )
    wrapping = _library(helpers, {})
    module = _library(library, {"evidence": evidence, "Pass": Pass, "logged": wrapping.logged})

    (step,) = StepRegistry.from_modules([module])

    # A new wrapper in helpers is a new fingerprint.
    both = library.read_bytes() + helpers.read_bytes()
    assert step.library_sha256 == hashlib.sha256(both).hexdigest()


def test_a_step_whose_library_cannot_be_read_has_no_fingerprint(tmp_path: Path) -> None:
    @evidence("m:e")
    def check() -> Outcome:
        return Pass()

    step = step_of(check)
    assert step is not None

    (registered,) = StepRegistry([step], {step: str(tmp_path / "gone.py")})

    assert registered.library_sha256 is None


def test_a_step_is_fingerprinted_once_its_registry_is_built() -> None:
    @evidence("m:e")
    def check() -> Outcome:
        return Pass()

    step = step_of(check)
    assert step is not None
    assert step.library_sha256 is None

    (registered,) = StepRegistry([step])

    assert registered == step  # the fingerprint is not what the step is
    assert registered.library_sha256 == SHA256


@pytest.mark.parametrize("candidate", [None, 1, "m:e", print, _no_parameters], ids=repr)
def test_anything_undeclared_is_not_a_step(candidate: object) -> None:
    assert step_of(candidate) is None


def _module(name: str, source: str) -> ModuleType:
    module = ModuleType(name)
    exec(textwrap.dedent(source), module.__dict__)
    return module


FIRST = """
    from jpipe_runner import Pass, evidence, strategy

    @evidence("m:e1", produces=["a"])
    def first():
        return Pass(a=1)

    def helper():
        return 1

    @strategy("m:s", consumes=["a"])
    def second(a):
        return Pass()
"""


def test_a_registry_lists_the_steps_of_its_modules_in_order() -> None:
    module = _module("first", FIRST)
    registry = StepRegistry.from_modules([module])
    assert [step.function for step in registry] == [module.first, module.second]
    assert len(registry) == 2
    assert repr(registry) == "StepRegistry(2 steps)"


def test_a_step_exposed_by_two_modules_is_listed_once() -> None:
    first = _module("first", FIRST)
    second = _module("second", "")
    second.reexported = first.first
    registry = StepRegistry.from_modules([second, first])
    assert [step.function for step in registry] == [first.first, first.second]


def test_a_registry_holds_declarations_and_two_are_independent() -> None:
    module = _module("first", FIRST)
    one, other = StepRegistry.from_modules([module]), StepRegistry.from_modules([module])
    assert one is not other
    assert one.steps == other.steps


def test_the_v3_api_says_what_replaced_it() -> None:
    with pytest.raises(ImportError, match="@evidence") as raised:
        importlib.import_module("jpipe_runner.framework.decorators.jpipe_decorator")
    assert raised.value.name == "jpipe_runner.framework"
    assert "jpipe_runner.framework" not in sys.modules


# --- What a step reads (JP027, ADR-0037) -----------------------------------------------------

coverage = 0.9
"""A global with the name of a parameter: reading it is not reading the parameter."""


def _declared(function: Callable[..., Outcome]) -> Step:
    found = step_of(function)
    assert found is not None
    return found


def test_a_parameter_never_read_is_unread() -> None:
    @strategy("s", consumes=["coverage", "threshold"])
    def ignores(coverage: float, threshold: float) -> Outcome:
        return Pass() if threshold else Fail("no threshold")

    assert _declared(ignores).unread.never == ("coverage",)


def test_an_observed_artifact_never_read_is_unread() -> None:
    @evidence("e", observes={"log": "CHANGELOG.md", "other": "README.md"}, produces=["x"])
    def unread(log: Path, other: Path) -> Outcome:
        return Pass(x=other.name)

    assert _declared(unread).unread.never == ("log",)


def test_a_global_of_the_same_name_is_not_the_parameter() -> None:
    @strategy("s", consumes=["coverage"])
    def reads_the_global(coverage: float) -> Outcome:
        return Pass() if globals()["coverage"] > 0.8 else Fail("low")

    assert _declared(reads_the_global).unread.never == ("coverage",)


def _helper(value: object) -> bool:
    return value is not None


@pytest.mark.parametrize(
    "function",
    [
        pytest.param(lambda a, b: Pass() if a > b else Fail("no"), id="directly"),
        pytest.param(lambda a, b: Pass() if (a, b) else Fail("no"), id="together"),
        pytest.param(lambda a, b: Pass() if [a + x for x in b] else Fail("no"), id="comprehension"),
        pytest.param(lambda a, b: Pass() if (lambda: a + b)() else Fail("no"), id="nested"),
        pytest.param(lambda a, b: Pass() if _helper(a) and _helper(b) else Fail("no"), id="helper"),
    ],
)
def test_a_parameter_read_in_any_way_is_read(function: Callable[..., Outcome]) -> None:
    declared = strategy("s", consumes=["a", "b"])(function)

    assert _declared(declared).unread.never == ()


def test_a_step_built_by_exec_is_checked_without_its_source() -> None:
    namespace: dict[str, Any] = {"Pass": Pass, "strategy": strategy}
    # A function with no source file, as one typed at a prompt.
    exec(
        '@strategy("s", consumes=["a", "b"])\ndef made(a, b):\n    return Pass(b=b)\n',
        namespace,
    )

    assert _declared(namespace["made"]).unread.never == ("a",)


def test_the_function_checked_is_the_one_declared_under_its_wrappers() -> None:
    def logged(function: Callable[..., Outcome]) -> Callable[..., Outcome]:
        @functools.wraps(function)
        def wrapper(**kwargs: Any) -> Outcome:
            return function(**kwargs)

        return wrapper

    @logged
    @strategy("above", consumes=["a"])
    def wrapped_above(a: int) -> Outcome:
        return Pass()

    @strategy("below", consumes=["a"])
    @logged
    def wrapped_below(a: int) -> Outcome:
        return Pass()

    assert _declared(wrapped_above).unread.never == ("a",)
    assert _declared(wrapped_below).unread.never == ("a",)


def test_what_only_kwargs_takes_is_unnamed_not_unread() -> None:
    @strategy("s", consumes=["a", "b"])
    def swallows(a: int, **kwargs: Any) -> Outcome:
        return Pass() if a else Fail("no")

    assert _declared(swallows).unread == Unread((), ("b",))


def test_a_callable_without_code_is_not_checked() -> None:
    @strategy("s", consumes=["a"])
    def plain(a: int) -> Outcome:
        return Pass()

    hidden = Step(Kind.STRATEGY, ("s",), plain, (Input("a", "a"),))
    plain.__wrapped__ = print  # type: ignore[attr-defined]

    assert hidden.unread == Unread()


def test_locals_hands_every_parameter_on() -> None:
    @strategy("s", consumes=["a", "b"])
    def forwards(a: int, b: int) -> Outcome:
        return Pass() if all(locals().values()) else Fail("no")

    assert _declared(forwards).unread.never == ()


def test_eval_may_read_every_parameter() -> None:
    @strategy("s", consumes=["coverage"])
    def evaluates(coverage: float) -> Outcome:
        return Pass() if eval("coverage > 0.8") else Fail("low")

    assert _declared(evaluates).unread.never == ()


def test_a_qualified_builtin_hands_every_parameter_on() -> None:
    @strategy("s", consumes=["a"])
    def qualified(a: int) -> Outcome:
        return Pass() if builtins.locals()["a"] else Fail("no")

    assert _declared(qualified).unread.never == ()


def test_a_frame_s_locals_hand_every_parameter_on() -> None:
    @strategy("s", consumes=["a", "b"])
    def introspects(a: int, b: int) -> Outcome:
        return Pass() if all(sys._getframe().f_locals.values()) else Fail("no")

    assert _declared(introspects).unread.never == ()


def test_a_positional_only_parameter_does_not_receive_its_keyword() -> None:
    @strategy("s", consumes=["a"])
    def shadowed(a: int = 0, /, **kwargs: Any) -> Outcome:
        return Pass() if a else Fail("no")

    assert _declared(shadowed).unread == Unread((), ("a",))


def test_unwrapping_stops_where_the_signature_does() -> None:
    def inner(x: int) -> Outcome:
        return Pass()

    @functools.wraps(inner)
    def adapted(a: int) -> Outcome:
        return inner(x=a)

    adapted.__signature__ = inspect.signature(adapted, follow_wrapped=False)  # type: ignore[attr-defined]

    assert _declared(strategy("s", consumes=["a"])(adapted)).unread == Unread()


def test_an_instruction_the_check_does_not_know_counts_as_a_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @strategy("s", consumes=["a"])
    def judged(a: int) -> Outcome:
        return Pass()

    unknown = types.SimpleNamespace(
        opname="FUTURE_FAST", opcode=dis.opmap["STORE_FAST"], argval="a"
    )
    monkeypatch.setattr(dis, "get_instructions", lambda code: iter([unknown]))

    assert _declared(judged).unread == Unread()
