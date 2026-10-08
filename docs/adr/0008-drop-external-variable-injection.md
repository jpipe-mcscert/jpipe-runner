---
status: accepted
date: 2026-10-08
decision-makers: Sébastien Mosser
---

# ADR-0008: Drop external variable injection

## Context and Problem Statement

v3 let a run inject values into the pipeline from outside the step library, through two
command-line options (`git show v3.6.0:src/jpipe_runner/runner.py`):

- `--config-file PATH` read a YAML file, and every top-level key became a variable;
- `--variable NAME:VALUE`, repeatable, added or overrode one, with the value parsed into a
  Python type by `parse_value`.

`PipelineEngine.load_config` wrote these values into the module-level context with
`ctx.set_from_config(key, value)`, which set the value on *the first function that had
declared the variable*. This had consequences that nothing documented:

- **Import order was load-bearing.** The decorators had to have filled `ctx` before
  `load_config` ran, or a configured key matched no declaration and silently vanished.
- **Variable names were one flat, process-wide namespace.** A configured key went to
  whichever step happened to be registered first.
- **A configured value was a producer the model did not show.** The dataflow validators
  had to treat config keys as producers, so a consumed variable could have its source in a
  file passed on the command line rather than in the justification.
- **Failures were logged, not raised.** A missing or malformed config file, or a key that
  could not be set, was logged and the run carried on without it.

Of the 14 v3 scenarios ported to v4 (`tests/e2e/scenarios/`), six used `config.yaml` or
`--variable`. Each ported cleanly: the value became a constant in the step library, or a
file the step reads, and the scenario's comments say which. v4 rebuilds the declaration
and the values from scratch (ADR-0006, ADR-0009). Should it keep injection (#114)?

## Decision Drivers

- **The justification shows where every value comes from.** Each variable is produced by a
  step bound to an element of the model, so the argument and its data agree.
- **No hidden state.** Nothing outside the model and the step library changes what a run
  computes, and no ordering between imports and configuration matters.
- **A step reads the world itself.** Evidence observes something: a file, a tool's output,
  an environment variable. That is where an input belongs, in code a reader can follow.
- **A small CLI.** Every option is a contract, kept in step with the Action and the docs.

## Considered Options

1. Keep `--config-file` and `--variable`, writing into the per-run `ValueStore`.
2. Keep them, but as a declared source: a pseudo-element or a reserved step that produces
   the configured variables.
3. Drop external injection: every value is produced by a step.

## Decision Outcome

Chosen option: **3, drop external injection**, because it is the only option where every
value in a run is produced by a step bound to an element of the model.

- `--variable` and `--config-file` do not exist in v4. The CLI (#124) does not add them.
- A step that needs an input reads it: a constant in the library, a file, or the
  environment. Evidence is the natural place, since evidence observes the world.
- `pyyaml` is no longer a dependency, and neither is `python3-yaml` in `debian/control`.
  Nothing else in v4 reads YAML.

### Consequences

- Good, because the dataflow validators (#119) have one kind of producer, a step, and
  "missing producer" means exactly that.
- Good, because a run is reproduced from the model, the library and the world the
  evidence observes, with no command line to recover.
- Good, because one runtime dependency less, for PyPI, Debian and Homebrew users alike.
- Bad, because a pipeline parameterised from the command line, such as a threshold changed
  per run, must now read it in a step, for example from an environment variable. The
  migration guide (#129) shows how.
- Bad, because a CI workflow that passed `--config-file` or `--variable` breaks on v4.
  Unknown options are rejected by the CLI, so the failure is immediate and explicit.

### Confirmation

- `pyproject.toml` and `debian/control` do not mention YAML, and
  `grep -rn yaml src/` comes back empty.
- The CLI (#124) has no option that sets a variable. Its tests and `docs/cli.md` (#127)
  list every option.

## Pros and Cons of the Options

### 1. Keep injection, into the `ValueStore`

- Good, because v3 workflows keep working.
- Bad, because a value would have no producing element, so provenance (ADR-0009) and the
  validators need a special case for it.
- Bad, because the run's result depends on a command line the report does not show.

### 2. Injection as a declared source

- Good, because injected values would have a producer that validation can see.
- Bad, because that producer is not in the justification: the model would still not say
  where the value comes from.
- Bad, because it adds a concept, a pseudo-element, to explain and maintain.

### 3. Drop injection

- Good, because the model, the library and the world are the only inputs of a run.
- Bad, because a few v3 libraries need a step that reads what the configuration supplied.

## More Information

- #114, where this was decided along with ADR-0006.
- ADR-0009 (#117): the per-run `ValueStore`, which holds only values produced by steps.
- The e2e scenarios that replaced configuration: `simple_success`, `complex_success`,
  `skip_scenario`, `missing_producer`, `self_dependency`, `exception_handling` (see the
  comments in their `scenario.toml` and `steps.py`).
