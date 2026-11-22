# Contributing

jPipe Runner is part of the [jPipe](https://www.jpipe.org) project. Bug reports, questions
and proposals are welcome as [issues](https://github.com/jpipe-mcscert/jpipe-runner/issues).

Pull requests are invite-only, as in every jPipe repository
([contributions are by invitation](https://github.com/jpipe-mcscert/.github/blob/main/CONTRIBUTING.md#contributions-are-by-invitation)):
only the maintainers and the collaborators they invite open one, and an unsolicited pull
request is closed without review. To contribute, open an issue first and discuss the
change there; if we agree on it, a maintainer invites you. Collaborators, too, open an
issue before starting anything larger than a fix, so that we can agree on the approach
before the code is written.

## Development setup

You need:

* **Python 3.11 or later.** CI tests on 3.11 to 3.15, and on 3.12 with the oldest
  dependencies too.
* **[Poetry](https://python-poetry.org) 2.x**, installed with [pipx](https://pipx.pypa.io):
  `pipx install poetry`. Avoid Homebrew's Poetry, which leaks system packages into its
  resolver.
* **[pre-commit](https://pre-commit.com)**, to run the linters before each commit:
  `pipx install pre-commit`.
* **The [Graphviz](https://graphviz.org/download/) `dot` program**, to render diagrams
  (`brew install graphviz` or `sudo apt-get install graphviz`). The tests that render an
  image are skipped without it.

Clone the repository and set up the environment:

```bash
git clone https://github.com/jpipe-mcscert/jpipe-runner.git
cd jpipe-runner
poetry env use python3.11   # only if `python3` on your PATH is older than 3.11
poetry install              # virtual environment with the runner (editable) and the dev tools
pre-commit install          # run ruff and mypy before each commit
```

Check that everything works by running what CI runs:

```bash
poetry run pytest                  # all tests, with coverage (writes coverage.xml)
poetry run pytest -m unit          # unit tests only
poetry run pytest -m e2e           # end-to-end tests only
poetry run ruff check .            # lint (add --fix to apply the safe fixes)
poetry run ruff format --check .   # formatting (drop --check to reformat)
poetry run mypy                    # type-check src/ in strict mode
```

Run the tools through `poetry run`, so that they use the project's environment and the
editable install of `src/`, not another `jpipe-runner` installed elsewhere. Their
configuration lives in [`pyproject.toml`](../pyproject.toml).

## Running your working copy

`poetry install` installs the runner in *editable* mode: the `jpipe-runner` command of the
project's environment runs the code under `src/` as it is on disk, so a change is live on
the next run, with nothing to reinstall. Start it with `poetry run`, from any directory
inside the repository:

```bash
poetry run jpipe-runner --version
poetry run python -m jpipe_runner --version   # the same command
```

A bare `jpipe-runner` is whichever one comes first on your `PATH`, often a released version
installed by Homebrew or pipx, which ignores your changes. `poetry run which jpipe-runner`
shows the one `poetry run` starts: it is in the project's virtual environment.

To try a change on a real justification, run one of the end-to-end scenarios, each a
directory with a compiled model (`justification.json`) and its step library (`steps.py`).
Run it from the scenario's directory, because the files the evidence observes are relative
to the working directory:

```bash
cd tests/e2e/scenarios/release_example
poetry run jpipe-runner --library steps.py justification.json
```

[`cli.md`](cli.md) describes the options. To work in a shell where `jpipe-runner` is the
development version, without the `poetry run` prefix, activate the environment:
`eval "$(poetry env activate)"`.

## Tests and checks

[`tests/README.md`](../tests/README.md) describes the test architecture: rule tests,
golden reports, property tests, and the scenario format. `poetry run pytest
--update-goldens` regenerates the golden reports and `docs/rules.md`; review the diff
before committing it. Pull requests go through a SonarCloud quality gate
([ADR-0004](adr/0004-sonarcloud-quality-gate.md)).

## Documentation

The documentation is Markdown under `docs/`, indexed in reading order by
[`docs/README.md`](README.md) ([ADR-0003](adr/0003-drop-sphinx-markdown-docs.md)). A
change that users can see is documented in the same pull request, with a page under
`docs/` for a new feature, and the [CHANGELOG](../CHANGELOG.md) says what it changes for
them. [`end-to-end.md`](end-to-end.md) follows one example through every stage: a change
to a stage updates its description there, with real output. Every code example and quoted
output on a page is checked by a test (`tests/unit/test_*_doc.py`), and so is every link:
an example that stops matching the code fails the build.

## Design documentation

[`design.md`](design.md) describes how the runner is built: a diagram of the modules, then
a class diagram. Update it in the same commit as a change to the design. A unit test,
`tests/unit/test_design_doc.py`, fails when the modules, the imports between them (the
solid arrows) or the classes of each module disagree with the code.

## Spelling

The project writes Canadian English: *colour*, *behaviour*, *centre*, *organize*, *analyze*,
*modelled*, *defence*, *licence* (the noun), *artifact*. This covers the documentation, the
CHANGELOG, docstrings, comments, messages and identifiers. Third-party text kept verbatim
and the keys of external formats (`license` in `pyproject.toml`) are left as they are.
[`tests/unit/test_spelling.py`](../tests/unit/test_spelling.py) checks it.

## Branches and pull requests

Branches, pull requests, releases and hotfixes follow the
[jPipe workflow](https://github.com/jpipe-mcscert/.github/blob/main/CONTRIBUTING.md),
shared by every repository of the organization: work branches are cut from `dev` and come
back through a pull request into `dev`, and a release is one pull request into `main`, from
a release branch, `release/X.Y.Z`, cut from `dev`. This section adds only what is specific
to jpipe-runner.

- **CI** (`ci.yml`: lint, types, tests) runs on every push to every branch.
- **The quality gate** is SonarCloud ([ADR-0004](adr/0004-sonarcloud-quality-gate.md)).
  The organization's plan analyzes pull requests and `main`, not other branches, so the
  `SonarQube` check appears once the draft pull request is open. A pull request from a
  fork gets no check, because it has no access to the token; a maintainer reviews its
  quality by hand.

### Releases

Cut `release/X.Y.Z` from `dev`, then, on it:

1. **Set the version** in `pyproject.toml`, the only place it is defined (`setup.py` reads
   it from there). Between releases `dev` carries a development version, `X.Y.Z.devN`
   (such as `4.1.0.dev0`), which the release workflow refuses to tag; replace it with the
   release's version: `X.Y.Z`, or `X.Y.ZaN` / `X.Y.ZrcN` for a pre-release. Follow
   [SemVer](https://semver.org): patch for fixes, minor for backward-compatible features,
   major for breaking changes.
2. **Update `CHANGELOG.md`**: move the `[Unreleased]` notes under a new
   `## [x.y.z] - YYYY-MM-DD` heading. Check what the dependency caps hold back with
   `poetry show --outdated`: Dependabot keeps `poetry.lock` fresh within the ranges, and a
   major is taken on a branch of its own
   ([ADR-0026](adr/0026-dependency-ranges-and-freshness.md)).
3. **Open the release pull request from `release/X.Y.Z` into `main`**, and take it through
   the workflow. Its diff is the whole release: what `dev` merged since the last one, and
   the release commit. A maintainer merges it.
4. **Tag the merge commit on `main`** and push the tag:
   ```bash
   git checkout main && git pull
   git tag vX.Y.Z          # must equal the pyproject.toml version
   git push origin vX.Y.Z
   ```
5. **Merge `main` back into `dev`**, which brings the release commit there, and set `dev`
   to the next development version (`X.Y.Z.dev0`), so that a build of `dev` never reports
   itself as the release.

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
