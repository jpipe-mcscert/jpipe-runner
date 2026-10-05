"""Hypothesis strategies for justification models (layer 3, see tests/README.md).

``justifications()`` draws well-formed models in the compiler's JSON format (ADR-0001):
``{name, type, elements[{id, label, type, aliases?, escaped?}], relations[{source, target}]}``.

The shape follows jPipe's structure: one conclusion, each claim (the conclusion or a
sub-conclusion) supported by exactly one strategy, and each strategy supported by evidence
and sub-conclusions. Evidence may also support further strategies, which turns the tree
into a DAG, as unification does in composed models.

Ids are drawn from a deliberately small vocabulary of ``:``-separated segments, so that
segment-suffix collisions (the hard case for binding resolution, #115) come up often.
Aliases model unified elements, which carry the ids of the originals they replaced.
The invariants are checked in tests/unit/test_strategies.py.
"""

from dataclasses import dataclass, field
from typing import Any

from hypothesis import strategies as st

EVIDENCE = "evidence"
STRATEGY = "strategy"
SUB_CONCLUSION = "sub-conclusion"
CONCLUSION = "conclusion"
KINDS = (EVIDENCE, STRATEGY, SUB_CONCLUSION, CONCLUSION)
CLAIMS = (CONCLUSION, SUB_CONCLUSION)

# Which kinds may support which: relations go from the supporting element to the claim.
SUPPORTS = {
    EVIDENCE: {STRATEGY},
    SUB_CONCLUSION: {STRATEGY},
    STRATEGY: {CONCLUSION, SUB_CONCLUSION},
    CONCLUSION: set(),
}

segments = st.text(alphabet="abcd", min_size=1, max_size=2)
labels = st.text(min_size=1, max_size=30).filter(lambda label: label.strip() != "")


@dataclass
class _Shape:
    """The model's structure before ids are assigned: kinds by index, and edges."""

    kinds: list[str] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)

    def add(self, kind: str) -> int:
        self.kinds.append(kind)
        return len(self.kinds) - 1


@st.composite
def _shapes(draw: st.DrawFn, max_depth: int, max_support: int) -> _Shape:
    shape = _Shape()

    def argue(claim: int, depth: int) -> None:
        strategy = shape.add(STRATEGY)
        shape.edges.append((strategy, claim))
        allowed = [EVIDENCE, SUB_CONCLUSION] if depth < max_depth else [EVIDENCE]
        for kind in draw(st.lists(st.sampled_from(allowed), min_size=1, max_size=max_support)):
            supporter = shape.add(kind)
            shape.edges.append((supporter, strategy))
            if kind == SUB_CONCLUSION:
                argue(supporter, depth + 1)

    argue(shape.add(CONCLUSION), depth=1)

    # Shared evidence: an evidence node is a source, so an extra edge from it cannot
    # create a cycle.
    evidence = [i for i, kind in enumerate(shape.kinds) if kind == EVIDENCE]
    strategies = [i for i, kind in enumerate(shape.kinds) if kind == STRATEGY]
    if len(strategies) > 1:
        extra = draw(
            st.lists(
                st.tuples(st.sampled_from(evidence), st.sampled_from(strategies)),
                max_size=3,
            )
        )
        shape.edges.extend(edge for edge in extra if edge not in shape.edges)
    return shape


@st.composite
def justifications(
    draw: st.DrawFn,
    *,
    max_depth: int = 2,
    max_support: int = 3,
    aliases: bool = True,
) -> dict[str, Any]:
    """A well-formed justification model, as the compiler would emit it."""
    shape = draw(_shapes(max_depth, max_support))
    name = draw(segments)
    size = len(shape.kinds)

    alias_counts = [draw(st.integers(0, 2)) if aliases else 0 for _ in range(size)]
    # A local id is one or two segments, so qualified ids have two or three segments in
    # total, like `release:e1` and `readiness:draft:tests`.
    local_ids = st.lists(segments, min_size=1, max_size=2).map(":".join)
    identifiers: list[str] = []
    for index in range(size + sum(alias_counts)):
        local = draw(local_ids)
        # Unique by construction rather than by filtering: a clash gets the index appended,
        # and digits never occur in drawn segments, so the result cannot clash again.
        identifiers.append(f"{local}{index}" if local in identifiers else local)
    qualified = [f"{name}:{local}" for local in identifiers]
    ids, spare = qualified[:size], iter(qualified[size:])
    with_escaped = draw(st.booleans())

    elements = []
    for index, kind in enumerate(shape.kinds):
        element: dict[str, Any] = {"id": ids[index], "label": draw(labels), "type": kind}
        if alias_counts[index]:
            element["aliases"] = [next(spare) for _ in range(alias_counts[index])]
        if with_escaped:  # the compiler emits it; the runner must accept and ignore it
            element["escaped"] = element["label"].lower().replace(" ", "_")
        elements.append(element)
    relations = [{"source": ids[source], "target": ids[target]} for source, target in shape.edges]

    return {
        "name": name,
        "type": "justification",
        # The compiler's output order carries no meaning; code must not depend on it.
        "elements": draw(st.permutations(elements)),
        "relations": draw(st.permutations(relations)),
    }
