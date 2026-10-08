---
status: accepted
date: 2026-10-08
decision-makers: Sébastien Mosser
---

# ADR-0007: Binding resolution, and why elements carry several ids

## Context and Problem Statement

A step names the elements it implements by id: `@evidence("release:e1")` (ADR-0006). The
runner must turn each such id into one element of the model, or say why it cannot.

This would be a dictionary lookup if every element had one id that step libraries used
verbatim. It has neither property, because of how the jPipe compiler composes models:

- **Composition merges elements and keeps their ids as aliases.** `Unifier` groups
  equivalent elements across source models (by default, same label), collapses each group
  into one element with a *minted* id (`unified_N`), and aliases every original id onto it.
  `refine` merges the hook and the refinement's conclusion into one sub-conclusion named
  `hook`, again aliasing both. The JSON carries these as `aliases`.
- **The compiler writes the originals, not the minted id.** `PythonExporter` emits one id
  per *authored* original of a merged element, since a minted id "names a group by a
  counter and appears in no source file".
- **The compiler shortens what it writes.** `AbstractModelExporter.minimalLink` cuts each
  id to the shortest tail of `:`-separated segments, at least `container:id`, that still
  designates one element. It checks that against the resolution rule below, by exact match
  first, then by unique strict suffix.

So a step library holds ids that are an element's id, one of its aliases, or a tail of
either. v3 (`git show v3.6.0:src/jpipe_runner/framework/engine.py`, `_resolve_node_id`)
resolved them with a rule specified by 609 lines of tests, but **silently ignored an id
that matched nothing**: `_resolve_node_id` returned `None`, the binding was skipped, and a
typo meant the step never ran and no one was told.

How should v4 resolve an id, and what should it do with one that resolves to no element,
to several, or with an element that two steps claim (#115)?

## Decision Drivers

- **The compiler and the runner agree.** Every id the compiler writes into a step library
  designates the element it was written for. The compiler's shortening and the runner's
  resolution are two halves of one contract.
- **An exactly named element is never shadowed** by an unrelated element whose id happens
  to end the same way.
- **Nothing resolves silently by guess.** An id that designates several elements is an
  error, not a choice.
- **Nothing fails silently either.** An id that designates nothing is reported.
- **Each element has at most one implementation, and each step implements one element.**

## Considered Options

1. Exact ids and aliases only.
2. v3's rule: exact, then qualified, then strict segment suffix, ported as is.
3. Fuzzy matching (edit distance, labels) as a fallback after v3's rule.

## Decision Outcome

Chosen option: **2, v3's rule**, because it is the rule the compiler shortens against, so it
is the only option under which every id the compiler writes resolves, and it never
guesses. Its silent cases become diagnostics.

An id designates an element by the first of these that matches (`Resolver.resolve`):

1. **exact**: the element's id or one of its aliases;
2. **qualified**: `<justification name>:<id>`, where `<id>` is exact;
3. **suffix**: a strictly shorter tail of the element's id or of an alias, cut at segment
   boundaries. `e_metric` and `r17:e_metric` designate `rigor:r17:e_metric`; `metric`
   (part of a segment) and `r17` (not a tail) do not. A tail of two different elements'
   ids raises `AmbiguousIdError`; two ids of the same element are not ambiguous.

For rule 2, v3 split the id at its *last* `:`, so it could only qualify a single-segment id
(`test:E1`). v4 strips the justification name as a prefix, so it also qualifies a
multi-segment one (`readiness:draft:tests` for an element whose id is `draft:tests`). The
compiler never relies on rule 2, since every id it exports is already qualified.

The model guarantees that an id or alias designates one element: a collision is refused
when the model is loaded (`JP002`, extended to aliases), as v3 did.

`BindingTable(justification, registry)` binds steps to elements **one to one** and collects
every problem as a diagnostic rather than stopping at the first:

| Code | When | Effect |
|---|---|---|
| **JP015** `UnknownBindingTarget` | an id designates no element | the id is ignored; the step's other ids may still bind it |
| **JP006** `AmbiguousBinding` | an id designates several elements, by suffix | the id is ignored |
| **JP007** `ConflictingBinding` | an element is designated by the ids of several steps | the element is left unbound |
| **JP007** `ConflictingBinding` | a step's ids designate several elements | the step is left unbound |

All three are errors (#119 turns them into rules). The second JP007 case is new in v4: v3
let one function implement several elements, which then produced the same variables twice.

### The hook's id survives `refine` (#116)

The cross-checks of #119 (JP008, JP016) assume that a step written against a model still
binds after that model is refined. `RefineOperator`'s javadoc says the hook and the
refinement's conclusion are *merged* into a sub-conclusion named `hook`, which would keep
the hook's id as an alias. The [refine tutorial](https://www.jpipe.org/tutorials/refine/)
says *"the black-box tests evidence is gone"*, which can be read as the id ceasing to exist.
Both cannot be true, so it was checked on 2026-10-08 with jPipe 2.5.0, on
`tests/e2e/scenarios/composed/refine.jd` (the tutorial's models):

```console
$ jpipe process -i refine.jd -m readiness -f JSON
```

The output is byte-identical to the committed `justification.json`, and the merged element
is:

```json
{ "id": "readiness:hook", "type": "sub-conclusion", "label": "The code is tested",
  "aliases": ["readiness:draft:tests", "readiness:tested:tested"] }
```

`jpipe process … -f PYTHON` writes both ids on the one (commented-out) sub-conclusion
function: `@jpipe_link("draft:tests")` and `@jpipe_link("tested:tested")`.

- **The javadoc is right.** The hook's id survives as an alias of the merged element, so
  `@evidence("draft:tests")` still binds, now to a sub-conclusion. That kind divergence is
  what JP008 reports (#119).
- **The tutorial is not wrong**, only silent about ids: the tests node is gone *as
  evidence*, replaced by an argued sub-conclusion. No correction is needed. The runner's
  own tutorial and authoring guide (#125, #126) say that the id keeps binding.
- **The refinement's conclusion is aliased onto the same element.** A step for
  `draft:tests` and another for `tested:tested` therefore claim one element: JP007, not a
  cross-check. The `composed` scenario binds only the first.

`tests/unit/test_binding.py` pins all three facts on the compiler's output.

### Consequences

- Good, because every link the compiler writes resolves to its element. A property test
  ports `minimalLink` and checks this over generated models.
- Good, because a typo in an id is reported, with the step's name, instead of the step
  quietly never running.
- Good, because a library written against a standalone model keeps binding after that
  model is composed: its ids become aliases or tails of aliases of the composed elements.
- Bad, because a suffix that is unique today can become ambiguous when the model grows. The
  JP006 message says to use a longer id, and the compiler regenerates minimal ones.
- Bad, because the rule has three steps to explain instead of one lookup. The authoring
  guide (#126) documents it.

### Confirmation

- `tests/unit/test_binding.py` pins the cases v3 tested (exact, alias, qualified, one- and
  two-segment suffix, middle and partial segments, exact over suffix, ambiguity through ids
  and through aliases) and each diagnostic of the table.
- `tests/unit/test_binding_properties.py` checks, over generated models with deliberately
  colliding ids: every id and alias designates its element; resolution agrees with this
  rule written as a declarative oracle; a resolved element is named or ended by the id; an
  ambiguous id lists every element it ends; every link `minimalLink` would write designates
  its element; and steps written with those links bind one to one with no diagnostic.
- `tests/unit/test_model.py` checks that an alias shared by two elements, or equal to
  another element's id, is JP002.

## Pros and Cons of the Options

### 1. Exact ids and aliases only

- Good, because it is one dictionary lookup.
- Bad, because the compiler writes shortened ids, which would not resolve.

### 2. v3's rule

- Good, because it is what the compiler shortens against, and is already specified.
- Good, because it never guesses: exact wins, and ambiguity is an error.
- Bad, because a suffix's meaning depends on the rest of the model.

### 3. Fuzzy fallback

- Good, because some typos would still bind.
- Bad, because a binding chosen by similarity is a guess, in a tool whose output is an
  assurance argument.

## More Information

- #115 (this decision); #119, where JP006, JP007 and JP015 become rules; #126, the authoring
  guide.
- `jpipe-compiler`: `Unifier.java` (minted ids and aliases), `RefineOperator.java` (the hook
  merge), `AbstractModelExporter.minimalLink()` and `PythonExporter.linksFor()` (what is
  written into a step library).
