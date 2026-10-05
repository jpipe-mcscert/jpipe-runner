# Contributing

If you are interested in contributing to this project, please contact the Jpipe-runner team at [Dr. Sébastien Mosser](mailto:mossers@mcmaster.ca).

## Branches

There is one long-lived branch, `main`, which holds the v4 rewrite that becomes 4.0.0.
The reasons are recorded in
[ADR-0014](adr/0014-trunk-with-milestone-branches.md).

| Branch | Role |
|--------|------|
| `main` | The trunk and the default branch. Releases are tags on it (`vX.Y.Z`). |
| `m<N>-<topic>` | One per v4 milestone, cut from `main`: `m0-foundation`, `m1-model`, …, `m7-docs`, `mb0-action-extraction`. MB1 (#132) is done in `jpipe-runner-action`, so it has no branch here. |
| `jpipe-runner-diagrams` | Written by the GitHub Action (generated diagram images). Not a development branch. |

### Working on a milestone

1. Work on the milestone's branch. Cut it from `main` if it does not exist yet. When it is
   first pushed, open its pull request into `main` **as a draft**, on the milestone's GitHub
   milestone, so that SonarCloud analyses every push
   ([ADR-0015](adr/0015-draft-pull-request-per-milestone.md)).
2. Commit each ticket as one or more commits. End the message of the commit that completes
   the ticket with `Closes #N`.
3. Push often. CI runs on every push to every branch, and the quality gate on every push to
   a branch with an open pull request.
4. When the milestone is complete, mark its pull request **ready for review**. The maintainer
   merges it with a merge commit, which keeps the per-ticket commits and closes their issues.

Work on one milestone at a time. If the next one has to start before the previous pull
request is merged, cut its branch from the previous milestone's branch. GitHub retargets
the second pull request to `main` once the first branch is deleted.

### Other pull requests

Open a separate pull request, from a short-lived branch, only when a change does not belong
to a milestone or needs a review of its own. Contributions from outside the maintainer team
always go through one. These pull requests are squash-merged.

### Releases

A release is a tag on `main`; it never needs a pull request of its own. The version bump
and the `CHANGELOG.md` entry go in as the last commit of the milestone being released (or
as a maintainer commit on `main`), then the maintainer tags. See the Releasing section of
the [README](../README.md).

## v3 is frozen at 3.6.0

v3 receives no further work:

- there is no maintenance branch — do not create a `release/3.x` (or similar) branch;
- nothing is cherry-picked or back-ported from `v4` to v3;
- there is no v3/v4 compatibility matrix to maintain.

v3 stays installable, from PyPI (`pip install jpipe-runner==3.6.0`) and from the
`v3.6.0` tag.

## Consulting the v3 code

v4 is a rewrite, not a port, so the v3 sources are not kept in the working tree. The
`v3.6.0` tag is the reference for how v3 behaved, permanently. Read it with
`git show v3.6.0:<path>`:

```bash
git show v3.6.0:src/jpipe_runner/framework/engine.py
```

This is *the* way to consult v3: do not check the old tree out beside the new one, and
do not copy v3 files back into the working tree to read them.

The same tag works with the rest of git when you need to find something first:

```bash
git ls-tree -r --name-only v3.6.0 -- src/      # list the v3 source files
git grep -n "PipelineEngine" v3.6.0 -- src/    # search the v3 sources
```
