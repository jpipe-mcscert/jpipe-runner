---
status: accepted
date: 2026-10-05
decision-makers: Sébastien Mosser
---

# ADR-0001: Consume compiler-produced JSON rather than parse `.jd`

This record is retroactive. The decision was taken in 2025 and never written down. It is
recorded here so that v4 builds on the reasoning instead of rediscovering it.

## Context and Problem Statement

A justification model is written in the jPipe language (`.jd` files). The runner has to
know its elements (evidence, strategies, sub-conclusions, conclusions) and the relations
between them before it can bind Python functions to them and execute them.

The runner originally parsed `.jd` itself. The first release (0.0.1, 2025-01-06) shipped a
Lark grammar (`jpipe_runner/jpipe.lark`, added in `f318cc4`), a parser and a transformer.
On 2025-06-25 commit `cb35f99` ("remove all deprecated class and files", #13) deleted all
three, 1071 lines in total. From then on the runner reads the JSON that the jPipe compiler
emits. That change was first released in **2.0.0** (2025-07-09) and reached `main` in the
squashed `release v3.0.0` commit (`9f8f41d`, 2025-08-08).

Nothing records why. Neither the 2.0.0 nor the 3.0.0 CHANGELOG entry mentions it, there
is no design document, and #13 only says to remove "v1-specific logic". The v2.0.0 CLI still
calls its argument `jd_file` and its help text still says "Path to the justification .jd
file", while the code rejects anything that does not end in `.json`.

The question the v4 rewrite has to answer again: should the runner read `.jd` source, or
the compiler's output?

## Decision Drivers

- **One definition of the language.** jPipe is defined by its compiler
  (`jpipe-mcscert/jpipe-compiler`). A second grammar in the runner drifts as soon as the
  language changes.
- **Composition.** `refine`, `assemble` and the `Unifier` merge elements, mint new ids
  (`unified_N`), register aliases, and change an element's kind (a refined hook becomes a
  sub-conclusion). Reimplementing these operators in Python would duplicate the hardest
  part of the compiler.
- **Load errors must be loud.** Whatever the input format, a malformed model must fail
  with a diagnostic, not run as an empty graph (see #112).
- **A stable, checkable interface** between the two tools.

## Considered Options

1. Parse `.jd` in the runner with its own grammar (v0.0.1 – 1.0.0).
2. Consume the JSON the compiler produces (2.0.0 onwards).
3. Embed or shell out to the compiler from the runner, taking `.jd` as input.

## Decision Outcome

Chosen option: **2, consume compiler-produced JSON.** The compiler is the only component
that knows the language and its composition operators. The runner takes their result as a
fixed interface:

```json
{ "name": "...", "type": "...",
  "elements":  [ { "id": "...", "label": "...", "type": "...", "aliases": ["..."] } ],
  "relations": [ { "source": "...", "target": "..." } ] }
```

v4 keeps this format unchanged and describes it with a JSON Schema
(`justification.schema.json`, #112).

### Consequences

- Good, because language changes and composition semantics live in one place. The runner
  sees composed models already flattened, with their aliases.
- Good, because the interface is small, versionable and can be validated with a schema.
- Bad, because the user runs two tools: compile `.jd` to JSON, then run the JSON.
- Bad, because the runner cannot point back to a line in the `.jd` source when it reports
  a diagnostic.
- Bad, because the coupling also runs the other way. The compiler generates the Python
  step library (`PythonExporter`), so the runner's authoring API is shared with the
  compiler, and changing it breaks both repositories.

### Confirmation

- No `.jd` grammar or parser exists in `src/`, and no parsing library is a dependency.
- The JSON loader validates its input against `justification.schema.json`. A malformed
  file produces a diagnostic and a non-zero exit (#112).

## Pros and Cons of the Options

### 1. Parse `.jd` in the runner

- Good, because a single tool takes the model straight from source.
- Bad, because the grammar duplicates the compiler's and drifts from it.
- Bad, because composition (`refine`, `assemble`, unification) would have to be
  reimplemented to run composed models at all.

### 3. Embed or shell out to the compiler

- Good, because users would keep a single command.
- Bad, because the runner would depend on a JVM toolchain. That is heavy for PyPI, PPA and
  Homebrew packages, and for the GitHub Action.
- Bad, because it does not remove the interface. It only hides it inside a subprocess.

## More Information

- Commits: `f318cc4` (grammar added), `cb35f99` (grammar removed, #13), `9f8f41d` (the
  v3.0.0 squash on `main`).
- #112 defines the v4 model and loader. #115 and ADR-0007 cover why composed elements
  carry several ids.
