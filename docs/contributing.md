# Contributing

If you are interested in contributing to this project, please contact the Jpipe-runner team at [Dr. Sébastien Mosser](mailto:mossers@mcmaster.ca).

## Branches

| Branch | Role |
|--------|------|
| `v4`   | Active development: the from-scratch rewrite that becomes 4.0.0. Branch from it and open pull requests against it. |
| `dev`  | The last v3 line. `v4` replaces it once v4 is feature-complete. |
| `main` | Released code. `v3.6.0` is the final v3 release. |

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
