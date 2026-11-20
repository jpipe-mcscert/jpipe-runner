# jpipe-runner documentation

Read the pages in this order. Each one links to the next where it needs it.

## Using the runner

1. [`tutorial.md`](tutorial.md): from a `.jd` file to a green run, on one page.
2. [`concepts.md`](concepts.md): the words the other pages use, each defined once.
3. [`authoring.md`](authoring.md): writing a step library, the reference.
4. [`observables.md`](observables.md): what an evidence observes, files, values and
   environment variables, what a path is relative to, and writing an observable.
5. [`cli.md`](cli.md): every option and exit code of `jpipe-runner`, and the `impact` and
   `status` subcommands.
6. [`rules.md`](rules.md): every diagnostic code, and how to fix what it reports.
7. [`report-schema.md`](report-schema.md): every field of the JSON report, for programs
   that read it.
8. [`events.md`](events.md): the events a run writes as it goes, for programs that show it
   while it runs, such as the IDE.
9. [`end-to-end.md`](end-to-end.md): one example followed through every stage, from the
   argument to its verdict, with the runner's real output.

Something does not work? [`troubleshooting.md`](troubleshooting.md) starts from what you
see. Coming from v3? [`migration-v3-v4.md`](migration-v3-v4.md) takes a v3 step library
and command line to v4.

## How the runner is built

- [`design.md`](design.md): the modules and classes, and how they fit together.
- [`adr/`](adr/README.md): the architecture decision records, why the runner is as it is.

## Working on the runner

- [`contributing.md`](contributing.md): branches, pull requests and releases.
- [`../tests/README.md`](../tests/README.md): the test architecture.
