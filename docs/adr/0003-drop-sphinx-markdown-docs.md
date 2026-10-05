---
status: accepted
date: 2026-10-05
decision-makers: Sébastien Mosser
---

# ADR-0003: Drop Sphinx; docs are task-oriented Markdown

## Context and Problem Statement

Since v3.0.0 the project has generated API documentation with Sphinx. Its sources were in
`docs/python_docs/`. The release workflow ran `sphinx-apidoc` and `sphinx-build` in a
`build-docs` job, and a `deploy-docs` job published the HTML to GitHub Pages
(<http://www.jpipe.org/jpipe-runner/>). That pulled in an optional `sphinx` dependency, two
Poetry extras (`docs` and `full`), and an `extras` input on the shared `setup-python-env`
action.

The generated site had been broken for several releases, and nothing noticed:

- `jpipe_runner.rst` autodocs `jpipe_runner.GraphWorkflowVisualizer`, a module removed with
  the GUI in 3.4.0.
- `conf.py` still declared `release = '2.0.0'` while 3.6.0 shipped.
- `jpipe_runner.framework.rst` autodocs `jpipe_runner.framework.validators` as a module.
  It became a package, so the per-rule docs in its submodules never appeared.
- The `.rst` stubs were last regenerated in the v3.0.0 squash (`9f8f41d`). `sphinx-apidoc`
  does not overwrite existing stubs, so the release job never refreshed them.

The documentation users actually needed (`README.md`, `docs/USAGE.md`, `docs/ACTION.md`,
`docs/TROUBLESHOOTING.md`) was already hand-written Markdown, read on GitHub.

What should documentation look like for v4?

## Decision Drivers

- The v4 public surface is small: a CLI and a Python API of four decorators plus three
  outcome types (#113, #114). Users need to know how to accomplish tasks, not what every
  internal symbol is.
- The documentation must not rot without anyone noticing. Whatever is published must be
  either written on purpose or generated from code that tests exercise.
- Fewer moving parts in the release pipeline, which publishes to four channels.
- Docs should be readable where the code is, on GitHub, with no build step.

## Considered Options

1. Keep Sphinx and fix it (stubs, version, packages).
2. Drop Sphinx; write task-oriented Markdown under `docs/`, read on GitHub.
3. Replace Sphinx with MkDocs Material plus `mkdocstrings`, deployed to GitHub Pages.

## Decision Outcome

Chosen option: **2, task-oriented Markdown.** The documentation is a short set of guides,
written in M7: a tutorial, the authoring API, the CLI, the report schema, and the rules
(#125–#129). The one reference that lists every item, `docs/rules.md`, is generated from
the `Rule` classes' metadata (#128), not by autodoc.

Removed in #110:

- `docs/python_docs/` and `docs/BUILD_DOCS.md`;
- the `sphinx` dependency and the `docs` and `full` extras in `pyproject.toml`;
- the `build-docs` and `deploy-docs` jobs in `release.yml`;
- the `extras` input of `.github/actions/setup-python-env`, which nothing else used.

### Consequences

- Good, because the release pipeline loses two jobs and a GitHub Pages deployment, which
  were the jobs most likely to fail for reasons unrelated to the code.
- Good, because the docs live beside the code and are reviewed in the same pull request.
- Good, because there is no generated output to go stale. The one generated page
  (`rules.md`) comes from metadata the tests exercise.
- Bad, because there is no browsable API reference. With four decorators and three
  outcome types, `docs/authoring.md` covers it.
- Bad, because the site at <http://www.jpipe.org/jpipe-runner/> is no longer redeployed. It
  keeps serving the last v3 build until the Pages site is unpublished or replaced. That is
  a repository setting, not something the code can do.

### Confirmation

- `grep -riI "sphinx\|python_docs"` over the repository finds nothing, outside the
  CHANGELOG, the ADRs (which record history), and third-party metadata in `poetry.lock`.
- `release.yml` has no job that builds or deploys documentation.

## Pros and Cons of the Options

### 1. Keep Sphinx and fix it

- Good, because the API reference and the published site are kept.
- Bad, because it repairs a tool sized for a library with a wide API, which this project
  is not.
- Bad, because autodoc output goes stale without anyone noticing, as v3 shows. Keeping it
  correct would need a check in CI.

### 3. MkDocs Material over the same Markdown

- Good, because it gives a searchable, styled site from the same files.
- Neutral, because it can be added later without rewriting anything: it reads the Markdown
  written under option 2.
- Bad, because it brings back a build-and-deploy job before there is any documentation
  for it to publish.

## More Information

- #110 removed Sphinx. #125–#129 write the v4 docs.
- If a published site is wanted later, option 3 can be added on top of this decision
  without superseding it.
