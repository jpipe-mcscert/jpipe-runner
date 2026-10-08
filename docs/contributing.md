# Contributing

If you are interested in contributing to this project, please contact the Jpipe-runner team at [Dr. Sébastien Mosser](mailto:mossers@mcmaster.ca).

## Development setup

The prerequisites, the installation steps and the commands CI runs are in the
[README](../README.md#development-setup).

[`tests/README.md`](../tests/README.md) describes the test architecture. Pull requests go
through a SonarCloud quality gate ([ADR-0004](adr/0004-sonarcloud-quality-gate.md)).

## Design documentation

[`design.md`](design.md) describes how the runner is built: a diagram of the modules, then
a class diagram. Update it in the same commit as a change to the design. A unit test,
`tests/unit/test_design_doc.py`, fails when the modules, the imports between them (the
solid arrows) or the classes of each module disagree with the code.

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
4. Before the milestone is complete, update the README's
   [*What v4 can do so far*](../README.md#what-v4-can-do-so-far) section: mark the
   milestone done in the status table, and list the features it added for users. Then
   update [`end-to-end.md`](end-to-end.md), which follows one example through every stage:
   describe the stages the milestone built as they now work, with real output.
5. When the milestone is complete, mark its pull request **ready for review**. The maintainer
   merges it with a merge commit, which keeps the per-ticket commits and closes their issues.

Work on one milestone at a time. If the next one has to start before the previous pull
request is merged, cut its branch from the previous milestone's branch. GitHub retargets
the second pull request to `main` once the first branch is deleted.

### Other pull requests

Open a separate pull request, from a short-lived branch, only when a change does not belong
to a milestone or needs a review of its own. Contributions from outside the maintainer team
always go through one. These pull requests are squash-merged.

### Releases

A release is a tag on `main`; it never needs a pull request of its own. Only a maintainer
pushes a release tag.

1. **Set the version** in `pyproject.toml`, the only place it is defined (`setup.py`
   reads it from there). Between releases the trunk carries a development version,
   `X.Y.Z.devN` (now `4.0.0.dev0`), which the release workflow refuses to tag; replace it
   with the release's version: `X.Y.Z`, or `X.Y.ZaN` / `X.Y.ZrcN` for a pre-release.
   Follow [SemVer](https://semver.org): patch for fixes, minor for backward-compatible
   features, major for breaking changes.
2. **Update `CHANGELOG.md`**: move the `[Unreleased]` notes under a new
   `## [x.y.z] - YYYY-MM-DD` heading.
3. **Land both on `main`**, as the last commit of the milestone being released or as a
   maintainer commit on `main`, and wait for CI to pass.
4. **Tag that commit** and push the tag:
   ```bash
   git checkout main && git pull
   git tag vX.Y.Z          # must equal the pyproject.toml version
   git push origin vX.Y.Z
   ```

The tag triggers [`release.yml`](../.github/workflows/release.yml). It checks that the
tag matches `pyproject.toml` (and fails at `validate-version` if not), runs the tests,
builds the wheel, sdist and signed Debian source package, and publishes them to GitHub
Releases, PyPI, the Ubuntu PPA (`ppa:mcscert/ppa`) and the Homebrew tap
(`jpipe-mcscert/mcscert`). A tag that is not a bare `X.Y.Z` is a pre-release: it goes to
PyPI and GitHub Releases only.

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
