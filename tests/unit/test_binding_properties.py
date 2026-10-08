"""Properties of binding resolution over generated models (layer 3, ADR-0007).

The oracle is the rule as ADR-0007 states it, written as a declarative filter over every
id and alias, independently of ``Resolver``'s indexes. The compiler's link shortening is
ported from ``AbstractModelExporter.minimalLink`` (jpipe-compiler 2.5.0), so the contract
between what the compiler writes into a step library and what the runner resolves is
tested on both sides of it.
"""

import json
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from jpipe_runner import Outcome, Pass, loader
from jpipe_runner.binding import AmbiguousIdError, BindingTable, Resolver
from jpipe_runner.model import Element, Justification, Kind
from jpipe_runner.steps import Step, StepRegistry
from tests.strategies import justifications, segments

AMBIGUOUS = "ambiguous"
COMPILER_MIN_SEGMENTS = 2


def _load(model: dict[str, Any]) -> Justification:
    return loader.loads(json.dumps(model))


def _is_strict_suffix(designator: str, key: str) -> bool:
    wanted, segments_ = designator.split(":"), key.split(":")
    return len(wanted) < len(segments_) and segments_[-len(wanted) :] == wanted


def _expected(justification: Justification, designator: str) -> Element | str | None:
    """What ADR-0007 says ``designator`` designates: an element, ``AMBIGUOUS``, or None."""
    exact = [element for element in justification if designator in element.ids]
    if exact:
        return exact[0]
    local = designator.removeprefix(f"{justification.name}:")
    qualified = [element for element in justification if local in element.ids]
    if local != designator and qualified:
        return qualified[0]
    by_suffix = [
        element
        for element in justification
        if any(_is_strict_suffix(designator, key) for key in element.ids)
    ]
    if len(by_suffix) > 1:
        return AMBIGUOUS
    return by_suffix[0] if by_suffix else None


def _resolved(resolver: Resolver, designator: str) -> Element | str | None:
    try:
        return resolver.resolve(designator)
    except AmbiguousIdError:
        return AMBIGUOUS


def _keys(justification: Justification) -> list[str]:
    return [key for element in justification for key in element.ids]


@st.composite
def _designators(draw: st.DrawFn, justification: Justification) -> str:
    """An id a step library might use: a key, a tail of one, a qualified one, or noise."""
    key = draw(st.sampled_from(_keys(justification)))
    parts = key.split(":")
    tail = ":".join(parts[draw(st.integers(0, len(parts) - 1)) :])
    noise = draw(st.lists(segments, min_size=1, max_size=4).map(":".join))
    return draw(st.sampled_from([key, tail, f"{justification.name}:{tail}", noise, noise[1:], ""]))


@given(justifications())
def test_every_id_and_alias_designates_its_element(model: dict[str, Any]) -> None:
    justification = _load(model)
    resolver = Resolver(justification)
    for element in justification:
        for key in element.ids:
            assert resolver.resolve(key) is element


@given(st.data())
def test_resolution_follows_the_rule(data: st.DataObject) -> None:
    justification = _load(data.draw(justifications()))
    resolver = Resolver(justification)
    for _ in range(10):
        designator = data.draw(_designators(justification))
        assert _resolved(resolver, designator) == _expected(justification, designator), designator


@given(st.data())
def test_a_resolved_element_is_named_or_ended_by_the_id(data: st.DataObject) -> None:
    justification = _load(data.draw(justifications()))
    designator = data.draw(_designators(justification))
    element = _resolved(Resolver(justification), designator)
    if isinstance(element, Element):
        local = designator.removeprefix(f"{justification.name}:")
        assert any(
            key in (designator, local) or _is_strict_suffix(designator, key) for key in element.ids
        )


@given(justifications())
def test_an_ambiguous_id_names_every_element_it_ends(model: dict[str, Any]) -> None:
    justification = _load(model)
    resolver = Resolver(justification)
    last_segments = sorted({key.rsplit(":", 1)[-1] for key in _keys(justification)})
    for designator in last_segments:
        if _expected(justification, designator) != AMBIGUOUS:
            continue
        ended = tuple(
            element
            for element in justification
            if any(_is_strict_suffix(designator, key) for key in element.ids)
        )
        with pytest.raises(AmbiguousIdError) as raised:
            resolver.resolve(designator)
        assert raised.value.candidates == ended


def _compiler_designated_by(index: dict[str, str], candidate: str) -> str | None:
    """``AbstractModelExporter.designatedBy``: exact, else one element by strict suffix."""
    if candidate in index:
        return index[candidate]
    found = {index[key] for key in index if _is_strict_suffix(candidate, key)}
    return found.pop() if len(found) == 1 else None


def _compiler_minimal_link(index: dict[str, str], key: str) -> str:
    """``AbstractModelExporter.minimalLink``: the shortest tail of at least two segments
    that still designates the same element, or the key itself."""
    parts = key.split(":")
    for length in range(COMPILER_MIN_SEGMENTS, len(parts)):
        candidate = ":".join(parts[-length:])
        if _compiler_designated_by(index, candidate) == index[key]:
            return candidate
    return key


@given(justifications())
def test_every_link_the_compiler_writes_designates_its_element(model: dict[str, Any]) -> None:
    justification = _load(model)
    index = {key: element.id for element in justification for key in element.ids}
    resolver = Resolver(justification)
    for element in justification:
        for key in element.ids:
            assert resolver.resolve(_compiler_minimal_link(index, key)) is element


def _step(*ids: str) -> Step:
    def check() -> Outcome:
        return Pass()

    return Step(Kind.EVIDENCE, ids, check)


@given(st.data())
def test_steps_written_with_compiler_links_bind_one_to_one(data: st.DataObject) -> None:
    justification = _load(data.draw(justifications()))
    index = {key: element.id for element in justification for key in element.ids}
    chosen = data.draw(st.lists(st.sampled_from(justification.elements), unique=True))
    steps = {
        element.id: _step(*dict.fromkeys(_compiler_minimal_link(index, k) for k in element.ids))
        for element in chosen
    }
    table = BindingTable(justification, StepRegistry(steps.values()))
    assert table.diagnostics == ()
    assert {binding.element.id: binding.step for binding in table} == steps
