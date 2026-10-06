---
status: accepted
date: 2026-10-06
decision-makers: Sébastien Mosser
---

# ADR-0016: Hide the graph inside `Justification`; no NetworkX type in the public API

## Context and Problem Statement

A justification is a directed graph: elements are nodes, and each relation goes from the
supporting element to the element it supports. #112 built `Justification` on a NetworkX
`DiGraph`, and exposed it as a public `Justification.graph` property. Within days, code
outside `model.py` depended on NetworkX through it:

- the unit tests of the model and the loader read `graph.edges`, called
  `nx.topological_sort` and `nx.is_directed_acyclic_graph` on it, and expected
  `nx.NetworkXError` when mutating it;
- callers had to know two private conventions: nodes are element ids, and each node keeps
  its `Element` under an `element` attribute;
- the order of `nx.topological_sort` is NetworkX's own, which nothing pins down. The golden
  reports of #133 need a deterministic order.

The executor (#120), the validation rules (#119) and the diagram export (#123) are about
to be written against the model. Whatever `Justification` exposes now is what they will
couple to. Should the graph, and the library behind it, be part of the model's public API?

## Decision Drivers

- **Information hiding.** The graph library is an implementation choice. Changing it, or
  changing how the graph is stored, must not ripple through the executor, the rules and
  the export.
- **A small public API in the model's terms.** Callers ask about supporters, the order of
  execution and cycles, not about nodes, edges and attributes.
- **Determinism.** Every sequence the model returns must have a defined order, so reports
  can be compared byte for byte.
- **Immutability.** A model does not change once loaded, and this must not depend on a
  feature of the graph library (`nx.freeze`).
- **Typing.** The code is type-checked with `mypy --strict`; the NetworkX stubs are partial,
  and their types should not spread through the code base.

## Considered Options

1. Keep `Justification.graph`: expose the frozen `DiGraph`.
2. Hide the graph: `Justification` answers graph questions in the model's terms, and
   NetworkX stays a private detail of `model.py`.
3. Drop NetworkX and write the graph algorithms in the project.

## Decision Outcome

Chosen option: **2, hide the graph**, because it is the only option that keeps the graph
library replaceable without making the project maintain its own graph algorithms.

`Justification` has no `graph` property. It answers, in model order (the order in which
the model lists its elements):

| Query | Returns |
|-------|---------|
| `supporters(id)` | The elements that directly support `id`. |
| `supported(id)` | The elements that `id` directly supports. |
| `topological_order()` | Every element after all of its supporters, ties broken by model order. `ValueError` on a cycle. |
| `cycle()` | The ids along one cycle, or `None`. |

A new need for the graph is met by a new query on `Justification`, in the same terms, never
by handing out the graph.

### Consequences

- Good, because NetworkX can be replaced, or the graph stored differently, by editing
  `model.py` alone.
- Good, because the order of every result is defined by the model, so reports are
  deterministic. The topological order breaks ties by model order
  (`lexicographical_topological_sort`).
- Good, because exceptions are the model's own: `KeyError` for an unknown id, `ValueError`
  for an order that does not exist. No caller catches a NetworkX exception.
- Good, because immutability no longer relies on `nx.freeze`: `Justification` has no
  method that changes it. The private graph is still frozen, as a safety net.
- Bad, because every new graph question needs a method on `Justification`. That is the
  point, but the API grows one query at a time.
- Bad, because code that wants an arbitrary NetworkX analysis must build its own graph
  from `Justification.relations`. Tests that use NetworkX as an independent oracle
  (`tests/unit/test_strategies.py`) do exactly that.

### Confirmation

`tests/unit/test_information_hiding.py` fails if:

- a module of `jpipe_runner` other than `model` imports NetworkX;
- a public function, constructor, method or property of the package mentions a NetworkX
  type in its signature.

## Pros and Cons of the Options

### 1. Keep `Justification.graph`

- Good, because it needs no code: every NetworkX algorithm is available to every caller.
- Bad, because NetworkX, its node-attribute conventions and its exceptions become part of
  the public API, and changing any of them breaks the executor, the rules and the export.
- Bad, because the order of results is whatever NetworkX does, which is not specified.

### 2. Hide the graph

- Good, because the public API is small, typed in the model's terms, and deterministic.
- Good, because NetworkX still does the graph algorithms, tested and maintained elsewhere.
- Bad, because each new query is a small wrapper to write and test.

### 3. Drop NetworkX

- Good, because it removes a runtime dependency, and from the Debian and Homebrew packages.
- Bad, because the project would maintain topological sorting and cycle finding itself.
  Option 2 makes this possible later, inside `model.py`, if the dependency ever becomes a
  problem.

## More Information

- #112, the model and loader, where the graph was first exposed.
- #119 (validation rules) and #120 (execution), the first callers of the queries above.
