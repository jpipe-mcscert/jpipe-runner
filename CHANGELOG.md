# Changelog

All notable changes to **jpipe-runner** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.5.1] - 2026-07-18

### Packaging
- Add the `questing` and `resolute` Ubuntu series to the PPA build matrix
  (`script/build-deb.sh`).
- Make the PPA upload (`script/publish-ppa.sh`) resilient: retry transient
  Launchpad upload errors, tolerate already-uploaded distros, and continue past a
  single failure so the Homebrew publish is not skipped.
- Re-release to complete the PPA and Homebrew publish that failed during 3.5.0
  (transient Launchpad `550` upload error). No functional code changes since 3.5.0.

_Contributors: Sébastien Mosser._

## [3.5.0] - 2026-07-18

### ⚠️ Breaking
- **GitHub Action input `python_path` changed meaning.** It now specifies one or
  more extra folders to add to Python's module search path (passed as
  `--python-path`), instead of selecting the Python interpreter. Interpreter
  selection has moved to the new `python_exec_path` input. Workflows that set
  `python_path` to a Python executable must rename that input to
  `python_exec_path` (#83, #95).

### Added
- New GitHub Action input `python_exec_path` to select the Python interpreter
  used to run jpipe-runner (#83).
- Suffix matching for `@jpipe_link` resolution, allowing functions to be bound by
  the tail of a qualified name (#96).
- Alias binding and suffix binding for `@jpipe_link`, with end-to-end coverage (#95).
- End-to-end integration tests exercising the GitHub Action (#90).

### Changed
- Refactored error handling for action inputs and log evaluation (#92).
- Log-grouping helper reworked behind an abstract interface (#87).
- Python-path default handling moved into a custom `argparse` action (#83).
- CI push triggers, import resolution, and alias handling improvements (#95).

### Fixed
- Local imports failing inside files loaded via the library loader (#76).
- Removed an unsupported deprecated parameter from `AppendElseDefaultAction` (#85, #86).

### Security
- Fixed a command-injection / quoting flaw in the GitHub Action runner script
  (`script/action/run_jpipe.sh`): the `jpipe_runner` command is now built as an
  argument array and executed directly instead of assembling a string and running
  it through `eval`. Action input values (variables, libraries, python paths) are
  passed as literal arguments and can no longer break quoting or execute shell
  code. Added a regression test in `tests/action/test_run_jpipe_script.py`
  (PR #97 review).

_Contributors: Corentin Veillard (@corentinVei), Sébastien Mosser._

## [3.4.1] - 2026-04-26

### Changed
- Refactored the validation layer and improved error handling (#73).

### Fixed
- Debian build: skip `dh_auto_test` to avoid a networkx import failure.
- Homebrew: build `rpds-py` from source with a Rust build dependency.
- Homebrew formula generation: prefer pre-built wheels over sdist.
- `update-homebrew`: install Poetry dependencies and guard against empty `RESOURCES`.

_Contributors: Sébastien Mosser._

## [3.4.0] - 2026-04-21

### Added
- `@jpipe_link` decorator for explicit binding of functions to pipeline nodes (#72).
- Validation of justification JSON files against a declarative JSON Schema (#71).

### Changed
- Documentation: removed all references to the decommissioned GUI.

_Contributors: Sébastien Mosser._

## [3.3.0] - 2026-04-17

### Changed
- Switched to pure-Python graphviz and fixed PPA build dependencies (#70).

### Fixed
- Release/Debian build: install `python3-tomli` via apt rather than pip.

_Contributors: Sébastien Mosser._

## [3.2.0] - 2026-04-17

### Changed
- Documentation improvements, logger fixes, and setup refactor (#69).

_Contributors: Sébastien Mosser._

## [3.1.0] - 2026-03-01

### Changed
- General maintenance release (#62).

_Contributors: Baptiste Lacroix._

## [3.0.1] - 2025-08-18

### Added
- Branding information for the GitHub Action.

_Contributors: Baptiste Lacroix._

## [3.0.0] - 2025-08-08

### Added
- Support for GitHub Actions log grouping (#7).

_Contributors: Baptiste Lacroix, Nicolas Lacroix._

## [2.0.0] - 2025-07-09

### Added
- User-specified variables injected into the runtime context.
- Execution workflow GUI for running pipelines interactively.
- Validators: duplicate-producer, produced-but-not-consumed, and a declarative
  justification JSON-schema validator, with unit tests (#21, #23, #24, #25).
- Multi-format diagram export (SVG and others) with status-based node/edge
  colouring and improved sub-conclusion styling (#14).
- Clearer error messages — including a specific message when a function returns a
  non-boolean value.

### Changed
- Full automated release pipeline: builds and publishes to PyPI (and TestPyPI),
  the Ubuntu PPA on Launchpad, and Homebrew, with Debian (`stdeb`) packaging and
  CI caching (#15).

### Fixed
- GitHub Action continues to the PR comment step even when `jpipe-runner` exits
  with an error.
- Config loading when a function only produces (and consumes nothing) (#9).
- Diagram download path and Graphviz install ordering in the action.

_Contributors: Baptiste Lacroix._

## [1.0.0] - 2025-03-17

### Added
- GitHub Actions log grouping for cleaner CI output (#7, #8).
- Custom Python-path support in the action (#4) and a `version` option.
- Example justification diagrams with a dedicated README (#2) and a Mermaid
  architecture flowchart (#5).
- Citation (BibTeX) metadata and future JSON helper functions.

### Changed
- Improved the `justify` process (#6) and snake_case conversion.
- Made Graphviz an optional dependency (#3).
- Raised the minimum supported Python to 3.10.

_Contributors: Jason Lyu, Sébastien Mosser, Nicolas Lacroix._

## [0.0.1] - 2025-01-06

### Added
- Initial implementation: the Lark-based jPipe grammar and parser, the runtime
  module, the core transformer and model/enum definitions, the exception
  hierarchy, a demo `action.yml`, and example justification diagrams.

_Contributors: Jason Lyu._

[3.5.0]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.4.1...v3.5.0
[3.4.1]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.4.0...v3.4.1
[3.4.0]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.3.0...v3.4.0
[3.3.0]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.2.0...v3.3.0
[3.2.0]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.0.1...v3.1.0
[3.0.1]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.0.0...v3.0.1
[3.0.0]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/jpipe-mcscert/jpipe-runner/compare/1.0.0...v2.0.0
[1.0.0]: https://github.com/jpipe-mcscert/jpipe-runner/compare/0.0.1...1.0.0
[0.0.1]: https://github.com/jpipe-mcscert/jpipe-runner/releases/tag/0.0.1
