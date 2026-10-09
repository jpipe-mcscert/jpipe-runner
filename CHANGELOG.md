# Changelog

All notable changes to **jpipe-runner** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_v4 is a from-scratch rewrite and a breaking release for every v3 user
([ADR-0002](docs/adr/0002-rewrite-from-scratch.md)). v3 stays installable as 3.6.0._

### Added
- **The `jpipe-runner` command, rebuilt for v4.** `jpipe-runner --library steps.py
  justification.json` loads the JSON the jPipe compiler wrote, imports the step libraries,
  validates them against the model, runs the steps and prints the text report;
  `python -m jpipe_runner` does the same. Its outputs are explicit: `--json` prints the
  JSON report on stdout instead of the text one, `--report PATH` writes the JSON report to
  a file, `--diagram PATH` draws the justification with the run over it, and
  `--dataflow PATH` its dataflow view, each in the format its suffix names (`dot`, `gif`,
  `jpeg`, `jpg`, `pdf`, `png` or `svg`). An output that cannot be written, such as a
  diagram whose suffix is not a format, is refused before any step runs, and so is a
  diagram that needs Graphviz when it is not installed. `--colour auto|always|never`
  chooses whether the text report is coloured (`always` suits GitHub Actions, which is
  not a terminal), and `--strict` counts warnings as errors and fails a skipped
  justification ([ADR-0023](docs/adr/0023-the-command-line.md)).
- **Exit codes a CI pipeline can act on**: 0 when the justification holds (or is skipped,
  unless `--strict`), 1 when it fails, 2 for a wrong command line, 3 when nothing could
  run (a refused model, a step library that cannot be imported, a validation error), and 4
  when a file cannot be read or written. v3 exited 1 for all of them.
- **A dry run that says what it checked.** `--dry-run` validates the step libraries
  against the model and calls no step. Its verdict is `valid` when validation finds no
  error, and the JSON report lists every element with its step and what that step
  declares, so `--dry-run --dataflow flow.svg` draws the declared dataflow without
  running anything. v3's dry run reported the justification as passed
  ([ADR-0024](docs/adr/0024-dry-run-verdict-and-both-diagrams.md)).
- **Logging that works.** `-v` logs what the run does on stderr (the model loaded, the
  libraries imported, each element's status, the Python that runs the steps), `-vv` adds
  details such as each step called and the python path, and `-q` shows errors only. v3's
  `--verbose` changed nothing that could be seen. stdout carries only the report.
- **Evidence declares the artifacts it observes.** `@evidence` takes
  `observes={"changelog": "CHANGELOG.md"}`, which maps a parameter of the function to the
  artifact it is to receive: a file, or the files a glob matches
  (`"build/reports/*.xml"`), relative to the directory the runner runs in. Every observed
  name must be a parameter of the function. An absolute path, or a directory (`"src/"`),
  is refused when the library is imported: observe the files a directory holds with a
  glob (`"src/**/*"`). **Every evidence must observe something**: one that observes
  nothing checks nothing in the world, and is an error (`JP018`). Existing evidence, and
  the skeletons jPipe 2.5.0 generates, must be given their artifacts. Before an evidence
  is called, each of its artifacts is checked and recorded, as its path, SHA-256 and size;
  one that is missing, unreadable or not a regular file, or a glob that matches nothing,
  fails the evidence without calling it (`JP019`)
  ([ADR-0018](docs/adr/0018-evidence-declares-observed-artifacts.md),
  [ADR-0019](docs/adr/0019-evidence-observes-files.md)).
- **Every element that did not pass says what stopped it.** An element skipped because
  something below it failed or skipped names that element, however far below, rather
  than its immediate supporter. A justification in which nothing failed but something was
  skipped is reported as skipped, not as passed
  ([ADR-0021](docs/adr/0021-execution-semantics.md)).
- **Diagrams are drawn as the jPipe compiler draws them, with the run over them.** A
  justification is drawn exactly as `jpipe process -f SVG` draws it (jPipe 2.5.0): element
  ids are kept as they are, rather than with `:` turned into `_`, labels are wrapped, and
  the shapes and colours are the compiler's. A run's statuses are drawn over it in the
  compiler's colour-blind-safe palette: a green border for a pass, a vermillion fill for a
  failure, a dashed grey node for a skip, with a thicker border for the element that
  started a chain of skips; in SVG, hovering a node shows its status and reason. v3's red
  and `#cccccc` overlay is gone. A new **dataflow view** also draws the files each evidence
  observes and the variables each step produces and consumes, with any variable that has
  no producer, no consumer or several producers, and any file that could not be read, in
  vermillion. Formats are `dot`, `gif`, `jpeg`, `jpg`, `pdf`, `png` and `svg`; `dot` is now
  the DOT text itself, without layout coordinates
  ([ADR-0022](docs/adr/0022-diagrams-follow-the-compiler.md)).
- **A JSON report, the machine-readable contract of a run.** It lists every element of the
  justification with its status, why it did not pass and what stopped it, the step bound
  to it and the ids that bound it (`bound_to`, `bound_by`, and the element's `aliases`, to
  explain a binding on a composed model), what that step declares it observes, consumes
  and produces, the values it produced, and each file it observed with its SHA-256 and
  size; then every diagnostic, with its traceback for an exception, a summary, the
  verdict, and where the diagrams were drawn. A run that stopped before any step ran is
  reported too. The report is
  deterministic (no time, relative paths), versioned by `schema_version` (`1.0`), and
  described by a JSON Schema shipped in the package, `jpipe_runner/schema/report.schema.json`;
  [`docs/report-schema.md`](docs/report-schema.md) documents it. Programs, such as the
  GitHub Action, should read it rather than the text output
  ([ADR-0011](docs/adr/0011-json-report-is-the-machine-readable-contract.md)).
- **A text report of the run, in the manner of Cucumber.** Each element is one line, in the
  order run: a symbol for its status (`✔`, `✘`, `-`), its kind, its label and its id. An
  element that did not pass says why underneath, and a failed evidence names the files it
  observed. The diagnostics follow, each with its fix and, for an exception, its traceback
  from the step's own code; then the summary and the verdict, last. A run that stopped
  before any step ran (a refused model, a library that cannot be imported, a validation
  error) is reported too, with its diagnostics. Colours are used only on a terminal, and
  never when `NO_COLOR` is set; the symbols fall back to ASCII where the terminal cannot
  show them. v3's ASCII banners and fixed-width table are gone. The layout is for people,
  and may change: scripts should read the JSON report.
- **A reference of the command line**, [`docs/cli.md`](docs/cli.md): every option, every
  exit code, where each output goes, and how a step library finds the packages it
  imports. Its examples are run by the test suite.
- **A reference of every diagnostic code**, [`docs/rules.md`](docs/rules.md): what each
  validation rule checks, why, its severity and how to fix what it reports, and the codes
  reported when a model or a step library is loaded, or a step runs. It is generated from
  the rules themselves, so it cannot drift from what the runner checks.

### Changed
- **The command line's options changed** (#124). `-v` is now `--verbose`; it was
  `--variable`, so a v3 command that injects a variable is now a usage error. `--library`
  is required. `--python-path` has no default: v3 made the working directory importable
  by default, and a library that imports a module next to it now needs `-p .`.
  `-o/--output-path`, a directory, and `-f/--format` are replaced by `--diagram PATH` and
  `--dataflow PATH`; `--diagram`, which v3 parsed and ignored, now names the file to draw.
  `-V` is gone. The justification no longer needs to end in `.json`: its content is
  checked, and a `.jd` file passed by mistake is refused (`JP001`) with a fix that says to
  compile it.
- **Steps are declared with one decorator per element kind.** `@evidence`, `@strategy`,
  `@sub_conclusion` and `@conclusion`, imported from `jpipe_runner`, replace `@jpipe` and
  `@jpipe_link`. They take the element ids as positional arguments, one or several, and
  the variables the step `consumes` and `produces`. Evidence cannot consume and a
  conclusion cannot produce. A step's parameters are the variables it consumes, and a
  mismatch is reported when the library is imported. Binding a conclusion or a
  sub-conclusion is optional; an unbound one takes its status from what supports it
  ([ADR-0006](docs/adr/0006-one-decorator-per-kind.md)). Step libraries written for v3,
  including those generated by jPipe 2.5.0 and earlier, must be updated: importing
  `jpipe_runner.framework` now raises an error that says what replaced it.
- **A function implements exactly one element, and an element has at most one function.**
  v3 let one function's ids bind several elements. Now that is an error (`JP007`), as is
  an element bound by two functions. Ids still resolve as in v3: exact id or alias, then
  `<justification>:<id>`, then a unique tail of `:`-separated segments
  ([ADR-0007](docs/adr/0007-binding-resolution.md)).
- **A step returns an outcome instead of a `bool`.** It returns `Pass()`, `Fail(reason)` or
  `Skip(reason)`, imported from `jpipe_runner`, and `Pass` carries the values the step
  produces: `Pass(coverage=92.0)` or `Pass({"coverage": 92.0})`. The injected `produce`
  parameter is gone, along with the rule that it be the last parameter. A step that still
  returns `True`, `False` or nothing is reported with `JP017`, whose fix names the outcome
  to return instead
  ([ADR-0005](docs/adr/0005-outcomes-as-return-values.md)).
- **Validation reports every problem at once, each with a code, and only errors stop a
  run.** v3 validators printed pre-formatted messages and counted a warning as a failure,
  so a clean library could fail on a warning. A problem is now a diagnostic with a stable
  code (`JPnnn`) and a severity: an error stops the run before any step executes, and a
  warning is reported while the run continues. No rule can be disabled
  ([ADR-0010](docs/adr/0010-diagnostics-as-data-rules-as-objects.md)).
- **Validation compares each step's kind with its element's.** Composition turns an
  evidence or a conclusion into a sub-conclusion (`refine`, `assemble`, unification), so a
  step written against a model before it was composed is declared with the old kind. That
  is a warning (`JP008`): the step runs after the sub-argument below it, as a
  cross-check. Any other mismatch, such as `@strategy` on an evidence, is an error
  (`JP016`) ([ADR-0013](docs/adr/0013-kind-divergence-under-composition.md)).
- **A consumed variable must be produced by a step that supports its consumer, directly
  or not** (`JP014`). v3 only checked that the producer came earlier in its execution
  order, so a consumer on another branch could run without its value when the producer
  failed. A step that consumes what it produces is reported the same way.
- **A strategy that ignores a value its supporters produce is a warning** (`JP013`), and
  only when another step reads that value: v3 made it an error. An evidence must still
  produce a value that another step consumes (`JP012`, an error), and a value that no step
  consumes is a warning (`JP011`).
- **A justification whose relations form a cycle is refused when it is loaded** (`JP004`),
  with the cycle it found, before any step library is bound. The jPipe compiler never
  emits a cycle, so such a file has been edited or corrupted.
- **A skipped step stops what it supports, as a failed one does.** In v3, a step skipped
  with `@skip` let the steps above it run, without the values it never produced. Now
  everything above a step that returns `Skip(...)` is skipped, and names it. A check meant
  to be optional should pass with what it found
  ([ADR-0021](docs/adr/0021-execution-semantics.md)).
- **A step that raises fails, and its traceback is kept** (`JP022`), starting in the
  step's own code. v3 kept only `TypeName: message`. A step that calls `sys.exit()` fails
  the same way instead of ending the run. A mistake in a step fails its element and the
  run goes on, so one run reports every broken step.
- **A `Pass` carries exactly the values the step declares.** One without a value listed
  in `produces` fails (`JP023`), since the steps that consume it could not run; one with
  a value that is not listed has it dropped, with a warning (`JP024`).
- **A step library is a module named after its file, and two libraries cannot share a
  name.** `steps.py` is imported as the module `steps`, registered in `sys.modules` (so a
  library may define a dataclass). v3 imported two libraries called `steps.py` and
  silently used the first one's functions; a library named like another library of the
  run, like a module Python already has (`json.py`), or with a file name that is not a
  Python identifier (`my-steps.py`) is now refused before anything is imported
  (`JP021`): rename the file ([ADR-0020](docs/adr/0020-importing-step-libraries.md)).
- **The Homebrew formula no longer depends on `libjpeg-turbo` and `freetype`.** They were
  needed by `matplotlib`, which only the GUI removed in 3.4.0 used, and no current
  dependency needs them.

### Removed
- **The `graphviz` Python package is no longer a dependency.** Diagrams are drawn by
  piping their DOT text to Graphviz's `dot` binary, as the jPipe compiler does, so only the
  binary is needed, as before. The Debian package depends on `graphviz` instead of
  `python3-graphviz`.
- **`@skip` and `@contribution`.** A step that should not run returns `Skip(reason)`,
  decided when it runs rather than when its module is imported. `@contribution` had no
  effect.
- **`--variable` and `--config-file`.** Values can no longer be injected from the command
  line or a YAML file: every variable is produced by a step, and a step that needs an input
  reads it from a file, a constant or the environment
  ([ADR-0008](docs/adr/0008-drop-external-variable-injection.md)). `PyYAML` is no longer a
  dependency.
- **The generated API documentation and the `docs` and `full` extras.**
  `pip install "jpipe-runner[docs]"` no longer installs Sphinx, and the API reference at
  <http://www.jpipe.org/jpipe-runner/> is no longer updated by releases. The v4
  documentation is task-oriented Markdown under `docs/`, read on GitHub
  ([ADR-0003](docs/adr/0003-drop-sphinx-markdown-docs.md)).
- **The v3 guides** `docs/USAGE.md`, `docs/ACTION.md`, `docs/TROUBLESHOOTING.md` and
  `docs/PACKAGING_RELEASE.md`. They described v3's CLI, Action and packaging, and are
  replaced by the v4 documentation. The v3 versions stay readable at the
  [`v3.6.0` tag](https://github.com/jpipe-mcscert/jpipe-runner/tree/v3.6.0/docs).

### Fixed
- **An id that matches no element is reported.** v3 silently ignored a `@jpipe_link` id
  that designated nothing, so a typo meant the function never ran and nothing said so. It
  is now an error (`JP015`) naming the function and the id.
- **A step may produce `None`.** v3 could not tell a variable that was never produced from
  one produced as `None`, and logged an error when a step consumed a legitimate `None`.
  Values are now kept per run, each with the element that produced it
  ([ADR-0009](docs/adr/0009-separate-registry-from-value-store.md)).
- **A step library that fails to import is reported** (#75). v3 caught only a
  `ValueError`, so an `ImportError`, a `SyntaxError` or a typo at module level escaped as
  a bare traceback, which GitHub Actions did not show. Every library is now imported, and
  each one that raises is reported with its exception and its line (`JP020`); nothing is
  validated or run. The python path is restored exactly after the run, even when a step
  raised or changed it.
- **A malformed justification file no longer runs as an empty justification.** v3 logged
  the problem, carried on with no elements, executed nothing and reported success. A file
  that is not UTF-8 JSON, does not have the compiler's format, has no elements, declares an
  element id twice or relates an element that does not exist now fails, and every problem
  in it is reported, each with its code (`JP001` to `JP003`). A template compiled to JSON
  is refused with a message saying that templates cannot be run.

## [3.6.0] - 2026-10-01

_This is the final release of the v3 line. v3 is now frozen: it stays installable from PyPI
and from the `v3.6.0` tag, but receives no further fixes. Development continues with v4._

### Added
- **`--quiet` / `-q` CLI flag.** Suppresses the startup ASCII banner and the banner printed
  ahead of the error log, leaving only the results and the messages themselves. Meant for
  output that is captured and re-published, such as the Action's PR comment.

### Fixed
- **Errors could be cut out of the PR comment.** To hide the banners, the Action dropped
  the first nine lines of the runner's output and everything from the logo onwards,
  whatever those lines actually contained. Output that did not have that exact shape —
  an exception raised while importing the step library, for example — lost the error
  message. The Action now runs the runner with `--quiet` and publishes its whole output,
  with only the colour codes removed, so the comment also includes the results table.
- **`dry_run: true` failed the Action on every run.** A dry run validates the justification
  and exits successfully without exporting a diagram, and the Action treated "no diagram"
  as a failure. A successful dry run is now reported as `result: 0`, and its PR comment
  says that the justification was validated but not executed. With `embed_image: true`,
  nothing is committed or embedded when there is no diagram.
- **Diagrams were silently dropped when the pattern matched more than one.** The Action
  kept only the first file `find` happened to return, so a run using the default
  `diagram: '*'` uploaded one arbitrary diagram (directory-order dependent) and discarded
  the rest. All generated diagrams are now kept: a single diagram is still uploaded
  unzipped, and multiple diagrams are uploaded together as one `jpipe-diagrams` artifact.
  New `diagram_count` and `diagram_dir` outputs expose the full set; `diagram_path` remains
  the primary diagram and is now chosen deterministically (first alphabetically).
- **Artifacts were named `<diagram>_.svg` on non-pull-request runs.** `COMMIT_SHA` came
  solely from `github.event.pull_request.head.sha`, which is empty for `workflow_dispatch`,
  `push` and `schedule`, leaving a dangling underscore. It now falls back to `github.sha`,
  and the suffix is omitted entirely when no SHA is available.
- **The runner's exit code is no longer masked when it produces no diagram.** That branch
  hard-coded `result=1`, so a runner failing with e.g. exit `2` was reported as `1` and the
  Action failed with the wrong code. The captured runner output is now reported on this
  path too — previously the PR comment showed an empty log for exactly the failure you most
  needed to diagnose.
- Diagram collection is limited to the top level of the output directory. It defaults to
  the runner workspace, which also holds the checked-out repository, so the previous
  recursive search could pick up unrelated `.svg` files from the project.
- **`docs/ACTION.md` pointed at a repository that does not exist.** The usage example used
  `jpipe-mcscert/jpipe-runner-action@main`, which 404s; the Action lives at the root of
  `jpipe-mcscert/jpipe-runner`. Anyone copy-pasting the old example got "repository not
  found".
- **`version` input was mis-documented** as a PyPI version (e.g. `0.0.1`). It is resolved as
  a **git ref** (tag such as `v3.5.3`, branch, or SHA).
- The PR comment no longer embeds a broken `![](null)` image when the image URL cannot be
  resolved: `build_comment.sh` now checks its API calls, retries the contents lookup to
  absorb the push/propagation race, assumes *private* when repository visibility is
  unknown (the public URL is guaranteed to 404 for a private repo), and degrades to a
  download link with a warning.

### Changed
- **The Action's `version` input now defaults to `v3.6.0` instead of `main`.** The Action
  used to install whatever runner was on `main` unless told otherwise. `main` will
  eventually hold v4, which this v3 Action cannot drive, so a workflow pinned only with
  `uses: jpipe-mcscert/jpipe-runner@v3.6.0` would have broken with no change on its side.
  It now installs the matching 3.6.0 runner. Workflows that relied on the default to pick
  up new runner changes no longer do; set `version` explicitly to track another ref.
- **The Action now needs a runner that understands `--quiet`, i.e. 3.6.0 or later.** It
  passes the flag on every run, so pinning the Action to `v3.6.0` while pinning its
  `version` input to an older runner (e.g. `v3.5.3`) fails with
  `unrecognized arguments: --quiet`. Leave `version` at its default, or pin both to the
  same tag.
- The diagram artifact is now uploaded **unzipped** (`upload-artifact` direct upload), so
  downloading it gives the image itself instead of a `.zip`.
  **Requires an Actions runner ≥ 2.327.1 (Node 24)** — GitHub-hosted runners are fine;
  self-hosted runners must be updated.
  Note: `gh run download` assumes artifacts are zips and fails on unzipped artifacts
  (`zip: not a valid zip file`); use the REST artifact endpoint instead. Browser downloads
  are unaffected. See the FAQ in `docs/ACTION.md`.
- The artifact upload is skipped when no diagram was produced, instead of failing the step.
- Rewrote `docs/ACTION.md` around usage rather than an option dump: summary, quick start,
  recipes, FAQ, with a complete input/output reference at the end. The Action's outputs
  (`result`, `diagram_path`, `pr_comment_id`) are now documented, and the permissions
  guidance is corrected — `contents: write` is needed **only** for `embed_image: true`.
- **Much quieter Action logs.** The dependency install no longer floods the workflow log:
  the step is wrapped in a collapsible group, `graphviz` is skipped entirely when `dot` is
  already on the runner, and apt/pip run quietly (~300 lines of `apt`/`dpkg` output and the
  pip progress chatter are gone). Errors and non-zero exits are still reported, so failures
  remain diagnosable.

### CI
- Bumped the last Node 20-era pins, in the root `action.yml` (missed by the 3.5.3 sweep,
  which only covered `.github/`): `setup-python@v6`, `upload-artifact@v7`,
  `github-script@v9`.
- Marked `script/action/*.sh` executable in git and dropped the four redundant `chmod +x`
  lines from `action.yml`.

_Contributors: Corentin Veillard (@corentinVei), Sébastien Mosser._

## [3.5.3] - 2026-07-18

### Fixed
- **PPA changelog no longer ships the packaging placeholder.** The release
  workflow now regenerates `debian/changelog` from scratch per Ubuntu series
  (`dch --create`) instead of prepending to the committed `0.0.0` base entry,
  which previously leaked into the source package and onto Launchpad.

### CI
- Bumped all GitHub Actions to their current Node 24 majors
  (`checkout@v5`, `setup-python@v6`, `upload-artifact@v7`, `download-artifact@v8`,
  `cache@v6`, `configure-pages@v6`, `upload-pages-artifact@v5`, `deploy-pages@v5`,
  `github-script@v9`, `softprops/action-gh-release@v3`) to clear the Node 20
  deprecation warnings.

## [3.5.2] - 2026-07-18

### Packaging / CI
- **Overhauled the release pipeline** to mirror the sibling `jpipe-compiler`,
  cutting `release.yml` roughly in half and removing two failure modes.
- Replaced the stdeb-generated Debian source tree with a committed static
  `debian/` directory (`control`, `rules`, `changelog`, `copyright`,
  `source/format`). `dpkg-buildpackage` now builds the source package directly;
  `script/build-deb.sh` and `stdeb.cfg` are removed.
- Moved the Ubuntu series list out of the shell script and into a
  `strategy.matrix` in `release.yml`, so each series builds and uploads in its own
  isolated, parallel job.
- **Dropped the `jammy` (22.04) PPA target.** It ships Python 3.10, but the project
  requires `>=3.11` (the pinned `networkx 3.5` will not install on 3.10), so the
  old jammy `.deb` was building against an incompatible networkx. The PPA now
  targets `noble`, `questing`, `resolute`, and `debian/control` enforces the floor
  via `X-Python3-Version: >= 3.11` (Depends now carries `python3 (>= 3.11~)`
  instead of a floorless `python3:any`).
- Added `python3-jsonschema` to the Debian runtime `Depends` (it was missing from
  the old `stdeb.cfg`) and shipped the JSON schema via `package_data`.
- Fixed the PPA upload that could **block indefinitely**: dropped the anonymous
  FTP `dput` configuration in favour of plain `dput ppa:` (default transport) per
  distro. `script/publish-ppa.sh` is removed.
- Decoupled the publish jobs (PyPI, PPA, Homebrew, docs) so a single flaky PPA
  upload no longer blocks unrelated publishes; PPA and Homebrew are gated to skip
  pre-release tags.
- Extracted the repeated Python/Poetry/graphviz setup into a
  `.github/actions/setup-python-env` composite action, reused by `ci.yml` and the
  release build jobs; removed the dangling `script/apt-packages.txt` cache key.

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

[Unreleased]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.6.0...HEAD
[3.6.0]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.5.3...v3.6.0
[3.5.3]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.5.2...v3.5.3
[3.5.2]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.5.1...v3.5.2
[3.5.1]: https://github.com/jpipe-mcscert/jpipe-runner/compare/v3.5.0...v3.5.1
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
