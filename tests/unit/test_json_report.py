"""The JSON report: the machine-readable contract of a run (#122, #145, ADR-0011).

Every scenario's report, whichever way its run ends, is checked against the schema the
package ships. The golden reports, which pin each scenario's whole document, arrive with
the command line (#124).
"""

import datetime
import hashlib
import json
from collections import OrderedDict
from pathlib import Path, PurePosixPath
from typing import Any

import pytest
from jsonschema import Draft202012Validator, ValidationError

from jpipe_runner import Pass, evidence, json_report, loader, strategy
from jpipe_runner.diagnostics import Diagnostic, Severity, user_traceback
from jpipe_runner.engine import Verdict, run
from jpipe_runner.json_report import SCHEMA, SCHEMA_VERSION, document, dumps, encoded
from jpipe_runner.libraries import LibraryLoadError
from jpipe_runner.model import InvalidJustificationError
from jpipe_runner.report import ElementReport, RunReport
from jpipe_runner.steps import StepRegistry, step_of
from tests.scenarios import Scenario, discover
from tests.unit.validation.builders import EVIDENCE, STRATEGY, element, model

VALIDATOR = Draft202012Validator(SCHEMA)
HERE = Path(__file__).parent


def _scenario_report(scenario: Scenario) -> RunReport:
    """The report of ``scenario``, whichever way its run ends."""
    try:
        justification = loader.load(scenario.justification)
    except InvalidJustificationError as error:
        return RunReport.refused(error)
    try:
        with scenario.imported_libraries() as modules:
            result = run(justification, StepRegistry.from_modules(modules), root=scenario.directory)
    except LibraryLoadError as error:
        return RunReport.not_imported(justification, error, root=scenario.directory)
    return RunReport.of(result, scenario.directory)


def test_the_schema_is_a_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(SCHEMA)


def test_the_schema_is_of_the_version_the_report_declares() -> None:
    assert SCHEMA["properties"]["schema_version"] == {"const": SCHEMA_VERSION}
    assert SCHEMA["title"].endswith(SCHEMA_VERSION)


@pytest.mark.parametrize("scenario", discover(), ids=lambda scenario: scenario.name)
def test_every_scenarios_report_matches_the_schema(scenario: Scenario) -> None:
    report = document(_scenario_report(scenario))

    VALIDATOR.validate(report)
    assert json.loads(json.dumps(report)) == report
    assert next(iter(report)) == "schema_version"


@pytest.mark.parametrize(
    "name", ["exception_handling", "unreachable_artifact", "composed"], ids=str
)
def test_a_report_is_the_same_on_every_run(name: str) -> None:
    (scenario,) = [s for s in discover() if s.name == name]

    first, second = (dumps(_scenario_report(scenario)) for _ in range(2))

    assert first == second


def test_a_report_holds_no_absolute_path() -> None:
    (scenario,) = [s for s in discover() if s.name == "exception_handling"]

    text = dumps(_scenario_report(scenario))

    assert str(scenario.directory) not in text
    assert '"file": "steps.py"' in text


def test_the_schema_refuses_an_undocumented_field() -> None:
    report = document(RunReport("m", Verdict.PASS))
    report["duration"] = 1.5

    with pytest.raises(ValidationError):
        VALIDATOR.validate(report)


def test_the_schema_refuses_a_reachable_artifact_without_its_digest() -> None:
    report = document(RunReport("m", Verdict.PASS))
    artifact = {"path": "a.txt", "reachable": True, "sha256": None, "size": None}
    report["elements"] = [_minimal_element() | {"artifacts": [artifact]}]

    with pytest.raises(ValidationError):
        VALIDATOR.validate(report)


def _minimal_element() -> dict[str, Any]:
    (written,) = document(RunReport("m", Verdict.PASS, (ElementReport("e", "e", EVIDENCE),)))[
        "elements"
    ]
    return written


# --- What an element says -------------------------------------------------------------------


@evidence("old:e", observes={"log": "log.txt"}, produces=["lines", "where"])
def observed(log: Path) -> Any:
    return Pass(lines=len(log.read_text(encoding="utf-8").splitlines()), where=log)


@strategy("s", consumes=["lines", "where"])
def judged(lines: int, where: Path) -> Any:
    return Pass()


@pytest.fixture
def element_document(tmp_path: Path) -> dict[str, Any]:
    (tmp_path / "log.txt").write_text("one\ntwo\n", encoding="utf-8")
    small = model(element("s", STRATEGY), element("e", EVIDENCE, "old:e"), relations=[("e", "s")])
    steps = [step_of(observed), step_of(judged)]
    result = run(small, StepRegistry(s for s in steps if s is not None), root=tmp_path)
    assert result.verdict is Verdict.PASS
    return {e["id"]: e for e in document(RunReport.of(result, tmp_path))["elements"]}["e"]


def test_an_element_says_what_bound_it_and_what_its_step_declares(
    element_document: dict[str, Any],
) -> None:
    assert {key: element_document[key] for key in ("aliases", "supports", "bound_by")} == {
        "aliases": ["old:e"],
        "supports": ["s"],
        "bound_by": ["old:e"],
    }
    assert element_document["bound_to"] == f"{__name__}.observed"
    assert (element_document["observes"], element_document["consumes"]) == (["log.txt"], [])
    assert element_document["produces"] == ["lines", "where"]


def test_an_element_lists_what_it_observed_and_produced(
    element_document: dict[str, Any], tmp_path: Path
) -> None:
    assert element_document["artifacts"] == [
        {
            "path": "log.txt",
            "reachable": True,
            "sha256": hashlib.sha256(b"one\ntwo\n").hexdigest(),
            "size": 8,
        }
    ]
    assert element_document["produced"] == {
        "lines": {"value": 2},
        "where": {"repr": "PosixPath('log.txt')", "type": "pathlib.PosixPath"},
    }


# --- Produced values ------------------------------------------------------------------------


class Opaque:
    def __repr__(self) -> str:
        raise RuntimeError("no repr")


@pytest.mark.parametrize(
    ("value", "written"),
    [
        pytest.param(None, {"value": None}, id="None"),
        pytest.param(True, {"value": True}, id="bool"),
        pytest.param(92.5, {"value": 92.5}, id="float"),
        pytest.param("2.0", {"value": "2.0"}, id="str"),
        pytest.param((1, [2, {"a": "b"}]), {"value": [1, [2, {"a": "b"}]]}, id="nested"),
        pytest.param(OrderedDict(a=1), {"value": {"a": 1}}, id="a mapping"),
        pytest.param(float("nan"), {"repr": "nan", "type": "float"}, id="NaN"),
        pytest.param({1: "a"}, {"repr": "{1: 'a'}", "type": "dict"}, id="a key that is not str"),
        pytest.param(
            PurePosixPath("a/b"),
            {"repr": "PurePosixPath('a/b')", "type": "pathlib.PurePosixPath"},
            id="a path",
        ),
        pytest.param(
            datetime.date(2026, 10, 9),
            {"repr": "datetime.date(2026, 10, 9)", "type": "datetime.date"},
            id="a date",
        ),
        pytest.param(
            Opaque(),
            {
                "repr": f"<{__name__}.Opaque object: repr() raised RuntimeError>",
                "type": f"{__name__}.Opaque",
            },
            id="a broken repr",
        ),
    ],
)
def test_a_produced_value_is_written_as_json_or_as_its_repr(value: Any, written: Any) -> None:
    assert encoded(value) == written


class Report:
    """An object with Python's default repr, which holds its address."""


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        pytest.param(Report(), f"<{__name__}.Report object>", id="an object's address"),
        pytest.param({"b", "a", "c"}, "{'a', 'b', 'c'}", id="a set, sorted"),
        pytest.param(frozenset({2, 1}), "frozenset({1, 2})", id="a frozenset, sorted"),
        pytest.param(set(), "set()", id="an empty set"),
        pytest.param((Report(),), f"(<{__name__}.Report object>,)", id="a tuple of one"),
        pytest.param({1: [Report()]}, f"{{1: [<{__name__}.Report object>]}}", id="nested"),
        pytest.param(
            [HERE / "steps.py", Path("/elsewhere/steps.py")],
            "[PosixPath('steps.py'), PosixPath('/elsewhere/steps.py')]",
            id="paths, relative to the root when under it",
        ),
    ],
)
def test_a_repr_is_the_same_on_every_run(value: Any, shown: str) -> None:
    assert encoded(value, HERE)["repr"] == shown


def test_a_value_that_contains_itself_is_written_as_its_repr() -> None:
    loop: list[Any] = []
    loop.append(loop)

    assert encoded(loop) == {"repr": "[[...]]", "type": "list"}


def test_a_long_repr_is_cut() -> None:
    written = encoded(PurePosixPath("x" * 5000))

    assert len(written["repr"]) == 1000
    assert written["repr"].endswith("…")


# --- Diagnostics ----------------------------------------------------------------------------


def _raised() -> BaseException:
    try:
        try:
            {}["missing"]
        except KeyError as inner:
            raise RuntimeError("broken") from inner
    except RuntimeError as outer:
        return outer


def test_a_diagnostic_carries_its_traceback_as_frames() -> None:
    raised = Diagnostic(
        "JP022", Severity.ERROR, "raised", "e", "Fix it.", user_traceback(_raised())
    )

    (written,) = document(RunReport("m", Verdict.FAIL, (), (raised,), root=HERE))["diagnostics"]

    assert {key: written[key] for key in ("code", "severity", "element", "message", "fix")} == {
        "code": "JP022",
        "severity": "error",
        "element": "e",
        "message": "raised",
        "fix": "Fix it.",
    }
    trace = written["traceback"]
    assert (trace["exception"], trace["message"]) == ("RuntimeError", "broken")
    (frame,) = trace["frames"]
    assert (frame["file"], frame["function"]) == ("test_json_report.py", "_raised")
    assert frame["code"] == 'raise RuntimeError("broken") from inner'
    assert trace["cause"]["exception"] == "KeyError"
    assert trace["cause"]["cause"] is None


def test_a_refused_model_has_no_justification_and_no_element() -> None:
    refused = RunReport.refused(
        InvalidJustificationError([Diagnostic("JP001", Severity.ERROR, "not JSON")])
    )

    written = document(refused)

    assert (written["justification"], written["verdict"], written["elements"]) == (
        None,
        "invalid",
        [],
    )
    assert written["summary"] == dict.fromkeys(
        ("elements", "pass", "fail", "skip", "not_run", "warnings"), 0
    ) | {"errors": 1}
    VALIDATOR.validate(written)


def test_the_text_of_a_report_is_its_document_indented() -> None:
    report = RunReport("m", Verdict.PASS).with_diagram("m.svg")

    text = json_report.dumps(report)

    assert text.endswith("}\n")
    assert json.loads(text) == document(report)
    assert '\n  "diagram": "m.svg"\n' in text
