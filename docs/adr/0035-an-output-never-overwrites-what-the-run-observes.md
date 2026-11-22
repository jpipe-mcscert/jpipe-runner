---
status: accepted
date: 2026-11-21
decision-makers: Sébastien Mosser
---

# ADR-0035: An output never overwrites what the run observes

## Context and Problem Statement

A run writes up to three files, which its options name: the JSON report (`--report`), the
diagram (`--diagram`) and the events (`--events`, [ADR-0030](0030-a-run-streams-its-events.md)).
Before anything runs, the command line refuses an output that would overwrite what the run
reads: the justification or a step library, a file a library's glob matches, or a link to one
([ADR-0023](0023-the-command-line.md), #182).

An output could still name a file an evidence observes. With the release example,
`jpipe-runner --library steps.py --events mock/junit.xml justification.json` emptied
`mock/junit.xml` before any step ran: the evidence then parsed JSON Lines instead of a JUnit
report, and the user's file was gone. `--report` and `--diagram` overwrote such a file when
the run ended: the run was right, and the artifact lost (#183).

What a run observes is known only once its step libraries are imported, which runs their code.
The outputs are checked before that, and the events file was opened, and emptied, before it
too, so that a file that cannot be opened stops the command before anything runs (ADR-0030).
How should the runner refuse an output that names an observed file, and what becomes of the
events written before the import?

## Decision Drivers

- **A run never destroys an artifact**, whatever its options say.
- **Nothing runs before a usage error**: no step, no validation.
- **An events file that cannot be opened stops the command before anything runs**, as
  ADR-0030 decided.
- **Every kind of observable is covered**: a file, a glob, a `JsonValue`'s file, what a
  library's observable depends on.

## Considered Options

1. Leave it as a user error, and say so in `docs/cli.md`.
2. Check the outputs once the libraries are imported, before validation; open the events
   file early without emptying it, and hold the events until the check passes.
3. A validation rule, a new `JPnnn`, that refuses a run whose outputs overlap what it
   observes.

## Decision Outcome

Chosen option: **2, check after the import**, because it is the only one that protects the
file while keeping ADR-0030's promise.

Once the step libraries are imported, and before validation, the command line compares each
output with what every step declares it observes, as the report names it: a path designates
its file, and a glob every file it matches, by name, so that an output that does not exist
yet is caught too, and by identity, so that a link is. `Env` observes no file; a library's
observable designates what `depends_on` returns. An output that names one is a usage error,
exit code 2, which names the output, what it designates and the step that observes it. A dry
run is refused the same way: it writes its outputs.

The events file is opened when the command starts, in append mode, so that one that cannot be
opened still stops it before anything runs, and is not emptied then. The stream holds its
events, `run.started` first, until the check passes: it then empties the file and writes them.
When the check refuses an output, the file is left as it was, and removed if the run created
it. A run that ends otherwise before the check, because the model is refused, a library
cannot be imported, or an input cannot be read, writes its events as before.

This amends ADR-0023, whose outputs were all checked before anything ran, and ADR-0030, whose
file was emptied, and whose `run.started` written, before the libraries were imported.

### Consequences

- Good, because no option of the runner overwrites an artifact a step observes.
- Good, because a file that cannot be opened still stops the command before anything runs.
- Neutral, because the check runs after the libraries are imported, so a library's import
  runs before it, as it did before a validation error.
- Bad, because `run.started` reaches the file once the libraries are imported, not before: a
  program that follows the run sees nothing while they load.
- Bad, because an observable of a library whose `depends_on` says nothing is not covered: the
  runner cannot see what it reads.

### Confirmation

`test_cli.py` checks that each output naming an observed file, a glob's future match, a
`JsonValue`'s file and a link to an observed file is refused with exit code 2, in a run and in
a dry run, and that the file is left as it was; and that a refused events file the run created
is removed. `test_events.py` checks that a run that cannot read an input still writes its
events.

## Pros and Cons of the Options

### 1. A user error

- Good, because nothing changes.
- Bad, because the runner destroys the user's file, silently for `--report` and `--diagram`.

### 2. Check after the import

- Good, because it covers every output, every observable that names its files, and dry runs.
- Bad, because the first events wait for the import.

### 3. A validation rule

- Good, because validation already sees what every bound step observes.
- Bad, because the engine would have to know the command line's outputs, which it does not.
- Bad, because the events file would still be emptied before the import.

## More Information

Issue #183, raised by the review of #182 (`--events`).
