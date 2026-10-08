import copy
import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from jsonschema import Draft202012Validator

from jpipe_runner import loader
from jpipe_runner.diagnostics import Severity
from jpipe_runner.model import InvalidJustificationError, Kind
from tests.strategies import justifications

VALID: dict[str, Any] = {
    "name": "release",
    "type": "justification",
    "elements": [
        {"id": "release:c", "label": "Ready", "type": "conclusion", "escaped": "ready"},
        {"id": "release:s", "label": "Check", "type": "strategy", "escaped": "check"},
        {
            "id": "release:e",
            "label": "Tests pass",
            "type": "evidence",
            "escaped": "tests_pass",
            "aliases": ["base:e", "other:e"],
        },
    ],
    "relations": [
        {"source": "release:e", "target": "release:s"},
        {"source": "release:s", "target": "release:c"},
    ],
}


def edited(**changes: Any) -> str:
    """VALID with top-level keys replaced (or removed, for ``None``), as JSON text."""
    document = copy.deepcopy(VALID)
    for key, value in changes.items():
        if value is None:
            del document[key]
        else:
            document[key] = value
    return json.dumps(document)


def element(index: int, **changes: Any) -> list[dict[str, Any]]:
    """VALID's elements, with the one at ``index`` edited (``None`` removes a key)."""
    elements = copy.deepcopy(VALID["elements"])
    for key, value in changes.items():
        if value is None:
            del elements[index][key]
        else:
            elements[index][key] = value
    return elements


def failure(text: str) -> list[tuple[str, str | None]]:
    with pytest.raises(InvalidJustificationError) as error:
        loader.loads(text)
    diagnostics = error.value.diagnostics
    assert diagnostics, "a load error always carries at least one diagnostic"
    assert all(d.severity is Severity.ERROR for d in diagnostics)
    return [(d.code, d.element) for d in diagnostics]


def test_the_schema_is_a_valid_2020_12_schema() -> None:
    Draft202012Validator.check_schema(loader.SCHEMA)


def test_a_compiler_model_loads() -> None:
    justification = loader.loads(json.dumps(VALID))
    assert justification.name == "release"
    assert [(e.id, e.kind) for e in justification.elements] == [
        ("release:c", Kind.CONCLUSION),
        ("release:s", Kind.STRATEGY),
        ("release:e", Kind.EVIDENCE),
    ]
    assert justification.element("release:e").aliases == ("base:e", "other:e")
    assert justification.element("release:c").aliases == ()
    assert justification.supporters("release:s") == (justification.element("release:e"),)
    assert justification.supporters("release:c") == (justification.element("release:s"),)


def test_properties_the_runner_does_not_use_are_ignored() -> None:
    elements = element(0, escaped=None, note="unused")
    relations = [{**r, "kind": "support"} for r in VALID["relations"]]
    justification = loader.loads(edited(elements=elements, relations=relations, version="2"))
    assert len(justification) == 3


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("{", [("JP001", None)], id="not JSON"),
        pytest.param("[]", [("JP001", None)], id="not an object"),
        pytest.param(edited(name=None), [("JP001", None)], id="no name"),
        pytest.param(edited(name=""), [("JP001", None)], id="empty name"),
        pytest.param(edited(type=None), [("JP001", None)], id="no type"),
        pytest.param(edited(elements=None), [("JP001", None)], id="no elements"),
        pytest.param(edited(relations=None), [("JP001", None)], id="no relations"),
        pytest.param(edited(elements=[], relations=[]), [("JP001", None)], id="empty model"),
        pytest.param(edited(elements={}), [("JP001", None)], id="elements not a list"),
        pytest.param(edited(elements=element(1, id=None)), [("JP001", None)], id="no id"),
        pytest.param(edited(elements=element(1, id=7)), [("JP001", None)], id="id not text"),
        pytest.param(
            edited(elements=element(1, label=None)), [("JP001", "release:s")], id="no label"
        ),
        pytest.param(
            edited(elements=element(1, type="claim")), [("JP001", "release:s")], id="unknown kind"
        ),
        pytest.param(
            edited(elements=element(2, aliases="base:e")),
            [("JP001", "release:e")],
            id="aliases not a list",
        ),
        pytest.param(
            edited(elements=element(2, aliases=["base:e", "base:e"])),
            [("JP001", "release:e")],
            id="repeated alias",
        ),
        pytest.param(
            edited(relations=[{"source": "release:e"}]), [("JP001", None)], id="no target"
        ),
        pytest.param(
            edited(elements=[*VALID["elements"], VALID["elements"][0]]),
            [("JP002", "release:c")],
            id="duplicate id",
        ),
        pytest.param(
            edited(relations=[{"source": "release:e", "target": "release:x"}]),
            [("JP003", None)],
            id="unknown relation target",
        ),
    ],
)
def test_a_malformed_model_is_reported(text: str, expected: list[tuple[str, str | None]]) -> None:
    assert failure(text) == expected


def test_every_schema_problem_is_reported_at_once() -> None:
    text = edited(name=None, elements=element(1, type="claim"), relations={})
    # In schema order: `required` (the name), then each property in turn.
    assert failure(text) == [("JP001", None), ("JP001", "release:s"), ("JP001", None)]


def test_structure_is_checked_only_once_the_schema_passes() -> None:
    elements = [*element(1, type="claim"), VALID["elements"][0]]
    assert failure(edited(elements=elements)) == [("JP001", "release:s")]


@pytest.mark.parametrize(
    "text",
    [
        pytest.param(edited(type="template"), id="template"),
        pytest.param(edited(elements=element(2, type="abstract-support")), id="abstract support"),
    ],
)
def test_a_template_is_refused_with_a_fix(text: str) -> None:
    with pytest.raises(InvalidJustificationError) as error:
        loader.loads(text)
    (diagnostic,) = error.value.diagnostics
    assert diagnostic.code == "JP001"
    assert diagnostic.fix is not None


def test_load_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "release.json"
    path.write_text(json.dumps(VALID), encoding="utf-8")
    assert loader.load(path).name == "release"
    assert loader.load(str(path)).name == "release"


def test_a_file_that_is_not_utf8_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "release.json"
    path.write_text(json.dumps(VALID), encoding="utf-16")
    with pytest.raises(InvalidJustificationError) as error:
        loader.load(path)
    assert [d.code for d in error.value.diagnostics] == ["JP001"]


def test_a_file_that_cannot_be_read_is_an_os_error(tmp_path: Path) -> None:
    # Not a diagnostic: an unreadable file is an I/O failure, with its own exit code (#124).
    with pytest.raises(FileNotFoundError):
        loader.load(tmp_path / "missing.json")


@given(justifications())
def test_every_well_formed_model_loads_as_written(document: dict[str, Any]) -> None:
    justification = loader.loads(json.dumps(document))
    assert justification.name == document["name"]
    assert [(e.id, e.label, e.kind.value, list(e.aliases)) for e in justification.elements] == [
        (e["id"], e["label"], e["type"], e.get("aliases", [])) for e in document["elements"]
    ]
    assert [(r.source, r.target) for r in justification.relations] == [
        (r["source"], r["target"]) for r in document["relations"]
    ]
    assert {(s.id, e.id) for e in justification for s in justification.supporters(e.id)} == {
        (r["source"], r["target"]) for r in document["relations"]
    }


@given(justifications())
def test_every_element_comes_after_its_supporters(document: dict[str, Any]) -> None:
    justification = loader.loads(json.dumps(document))
    order = justification.topological_order()
    position = {element.id: index for index, element in enumerate(order)}
    assert sorted(position) == sorted(element.id for element in justification)
    for element in justification:
        for supporter in justification.supporters(element.id):
            assert position[supporter.id] < position[element.id]
