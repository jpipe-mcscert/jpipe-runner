---
status: accepted
date: 2026-10-09
decision-makers: Sébastien Mosser
---

# ADR-0020: Import step libraries as modules named after their files, for one run

## Context and Problem Statement

A run imports the step libraries it is given (`--library`), and calls their steps. v3's
`PythonRuntime` got three things wrong (#120):

- **Modules were named by their file's basename and never entered into `sys.modules`.**
  Two libraries with one basename were both imported, and looking a function up by name
  silently took the first. A library that defines a `dataclass` fails to import without
  its module in `sys.modules`.
- **A library that raised when it was imported escaped as a bare traceback** (#75). Only
  a `ValueError` was caught, and in GitHub Actions the traceback did not even reach the
  log: the user saw `exit code 1`.
- **`sys.path` was changed around each import and each call**, then restored from a copy:
  correct, but done anew for every step.

v4 also needs two runs in one process to share nothing (ADR-0009): the test suite runs
every scenario's libraries in one process, and several of them are called `steps.py`.

How should a run import its step libraries, name them, and undo what it changed?

## Decision Drivers

- **A load-time error is reported, always**, with where it happened, like every other
  problem the runner finds (ADR-0010).
- **No silent first-wins.** Two libraries that would be confused are an error.
- **Reports name a step as its author knows it**, `steps.the_test_suite_passes`.
- **A library is a normal Python module**: a dataclass, `pickle` or a self-import work.
- **A run leaves the process as it found it.**

## Considered Options

1. Name each module after its file (`steps`), register it in `sys.modules`, and refuse a
   name that would be ambiguous.
2. Give each module a unique synthetic name (`_jpipe_library_0`), so no name can clash.
3. Keep v3's loading, and catch every exception it raises.

## Decision Outcome

Chosen option: **1, modules named after their files, for the duration of the run**,
because it is the only one that keeps the names authors see in reports and tracebacks
while making a clash an error rather than a guess.

- **`imported(libraries, python_path)` is a context manager**, and the run happens inside
  it. A step that imports a helper when it is called finds it as it would have when the
  library was imported.
- **A library is the module named after its file**, without `.py`, registered in
  `sys.modules` before its code runs, as `import` does.
- **A name that cannot be used is refused before anything is imported**, with `JP021`
  `UnusableLibraryName`: two libraries with the same name, a name that another module
  already has (imported, or found on `sys.path`, such as `json`), or a file name that is
  not a Python identifier. A library found on the python path under its own name is the
  same module, and is not a clash.
- **Every library is imported, and each that raises is reported**, with `JP020`
  `LibraryImportFailed`, at the line of the library where it failed. `SyntaxError`,
  `ModuleNotFoundError`, a `TypeError` from a step decorator and `SystemExit` are all
  reported this way; `KeyboardInterrupt` still stops the runner. The diagnostics are
  raised together in a `LibraryLoadError`, which also keeps each traceback, structured
  and trimmed to the library's frames. Nothing is validated or run: with a library
  missing, validation would report its steps as unbound.
- **A library that is not a file**, or a python path that is not a directory, is an
  `OSError`, as an unreadable model is: the runner was invoked wrongly.
- **`python_path` entries come first on `sys.path` while the run lasts.** On exit,
  `sys.path` is restored to the list it was, in place, whatever happened: an exception,
  or a step that changed it. No other directory is added: a library's own directory is
  not importable unless it is on the python path.
- **A library another library of the run has already imported**, from the python path,
  is that module: it is not run a second time, which would repeat its side effects and
  give its steps a second set of functions.
- **On exit, the libraries leave `sys.modules`**, with every module imported from a
  python path entry during the run, namespace packages included. Modules imported from elsewhere, such as third-party
  packages a step imported, stay cached: re-importing a C extension in the same process
  breaks it.

### Consequences

- Good, because a broken library is reported with a code and a line, in every
  environment, and with every other broken library.
- Good, because reports and tracebacks show `steps.function` and the library's file.
- Good, because a library behaves as a module Python imported.
- Bad, because a library cannot be called `json.py`, nor share its file name with
  another library of the run: it must be renamed.
- Neutral, because a run must happen inside the context; the CLI does it in one place.

### Confirmation

- `tests/unit/test_libraries.py` checks the names, `sys.path`, `sys.modules`, and every
  refusal and import failure.
- The `import_error` scenario checks a library that imports a missing module (#75).
- `tests/unit/test_scenario_corpus.py` imports every scenario's libraries with the real
  loader, in one process.

## Pros and Cons of the Options

### 1. Named after their files, clashes refused

- Good, because names are the ones authors know.
- Bad, because some file names must be changed.

### 2. Synthetic names

- Good, because no two libraries can clash.
- Bad, because reports and tracebacks show `_jpipe_library_0.function`.
- Bad, because a library cannot import a sibling library by name.

### 3. v3's loading, with every exception caught

- Good, because it is the smallest change.
- Bad, because two libraries with one name are still confused, and a library that
  defines a dataclass still fails.

## More Information

- #120, #75 (v3); [ADR-0009](0009-separate-registry-from-value-store.md), nothing
  outlives a run; [ADR-0010](0010-diagnostics-as-data-rules-as-objects.md), diagnostics.
