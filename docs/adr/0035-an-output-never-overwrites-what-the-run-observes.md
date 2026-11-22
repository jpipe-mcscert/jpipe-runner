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
   file at once, and hold its events until the check passes when emptying it could destroy
   something.
3. A validation rule, a new `JPnnn`, that refuses a run whose outputs overlap what it
   observes.

## Decision Outcome

Chosen option: **2, check after the import**, because it is the only one that protects the
file while keeping ADR-0030's promise.

Once the step libraries are imported, and before validation, the command line compares each
output with what every step bound to the justification declares it observes, as the report
names it: a path designates its file, and a glob every file it matches, by name, once the
output is resolved under the run's root, so that an output that does not exist yet, or is
reached through a linked directory, is caught, and by identity, so that a link is. An output
outside the root matches no glob. `Env` observes no file; a library's observable designates
what `depends_on` returns. A step bound to no element observes nothing in this run, and is
not checked. An output that names an observed file is a usage error, exit code 2, which names
the output, what it designates and the step that observes it. A dry run is refused the same
way: it writes its outputs. The diagram drawn before the first step
([ADR-0032](0032-a-run-previews-its-diagram.md)) is checked by the same rule.

The events file is opened when the command starts, so that one that cannot be opened still
stops it before anything runs. A new file, an empty one, a previous run's events (its first
line a `run.started` event), and anything that is not a regular file, such as a pipe, are
emptied and written at once, as before: a program that follows the file never reads a
previous run's events as this one's, and `run.started` arrives before the libraries are
imported. Only a regular file that holds something else, which can only be a mistake, is
opened without being emptied: the stream holds its events until the check passes, then
empties the file and writes them. When the check refuses an output, the events file is left
as it was, and removed, with the directories made for it, if the run created it. When the run
ends before the check, because the model is refused or a library cannot be imported, nothing
tells whether a step would observe a held file: it is left as it was, the error says so, and
the command exits with code 4.

This amends ADR-0023, whose outputs were all checked before anything ran, and ADR-0030, whose
file was always emptied before the libraries were imported.

### Consequences

- Good, because no option of the runner overwrites an artifact a step observes.
- Good, because a file that cannot be opened still stops the command before anything runs.
- Neutral, because the check runs after the libraries are imported, so a library's import
  runs before it, as it did before a validation error.
- Neutral, because a file that holds something other than events gets its events only once
  the libraries are imported, and none if the run ends before the check.
- Bad, because a run that ends before the check, its model refused or a library not
  imported, writes `--report` and `--diagram` unchecked: nothing says what it would observe.
- Bad, because an observable of a library whose `depends_on` says nothing is not covered: the
  runner cannot see what it reads.

### Confirmation

`test_cli.py` checks that each output naming an observed file, a glob's future match, a
`JsonValue`'s file and a link to an observed file is refused with exit code 2, in a run and in
a dry run, and that the file is left as it was; and that a refused events file the run created
is removed, with its directories. It also checks that a step bound to no element, and an
output outside the root, are not refused; that an output through a linked directory is; that
a previous run's events are emptied before the libraries are imported; that events reach a
named pipe; and that a file with other content is left as it was when the model is refused.

## Pros and Cons of the Options

### 1. A user error

- Good, because nothing changes.
- Bad, because the runner destroys the user's file, silently for `--report` and `--diagram`.

### 2. Check after the import

- Good, because it covers every output, every observable that names its files, and dry runs.
- Bad, because the first events of a file that holds something else wait for the import.

### 3. A validation rule

- Good, because validation already sees what every bound step observes.
- Bad, because the engine would have to know the command line's outputs, which it does not.
- Bad, because the events file would still be emptied before the import.

## More Information

Issue #183, raised by the review of #182 (`--events`).
