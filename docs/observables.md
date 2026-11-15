# Observing the world

Evidence is where an argument touches the world: a test report, a version number, the
branch a pipeline runs on. An evidence step does not go and read these itself. It
**declares** what it observes, and the runner observes it, records it in the report, and
passes it to the step. This page is the reference for that mechanism: what can be
observed, what a path is relative to, what the report records, and how to observe
something the runner has no class for.

The words are defined in [`concepts.md`](concepts.md); the decorators are in
[`authoring.md`](authoring.md). The decisions behind this page are
[ADR-0018](adr/0018-evidence-declares-observed-artifacts.md) and
[ADR-0028](adr/0028-observables-and-file-relative-paths.md).

## One example

The examples of this page run on one small project:

```
justification.json
checks/
  steps.py
mock/
  package.json
  CHANGELOG.md
```

Its step library is `checks/steps.py`:

```python
"""Step library for observables: evidence that observes more than files."""

from pathlib import Path

from jpipe_runner import Env, Fail, JsonValue, Outcome, Pass, evidence, strategy


@evidence(
    "version",
    observes={
        "version": JsonValue("../mock/package.json", "/version"),
        "changelog": "../mock/CHANGELOG.md",
    },
    produces=["announced"],
)
def the_package_announces_the_version(version: str, changelog: Path) -> Outcome:
    """The version of the package is the one the changelog opens with."""
    heading = changelog.read_text(encoding="utf-8").splitlines()[0]
    return Pass(announced=heading == f"## {version}")


@evidence("environment", observes={"path": Env("PATH")}, produces=["commands_found"])
def commands_are_found(path: str) -> Outcome:
    """The environment says where commands are."""
    return Pass(commands_found=bool(path))


@strategy("gates", consumes=["announced", "commands_found"])
def every_gate_passes(announced: bool, commands_found: bool) -> Outcome:
    """Both gates hold."""
    return Pass() if announced and commands_found else Fail("a release gate did not pass")
```

`observes` maps each parameter of the function to what it receives. The first evidence
receives a value read in a JSON file and the path of a file; the second receives the value
of an environment variable. Neither opens a path it was not given.

```console
$ jpipe-runner --library checks/steps.py --report report.json justification.json
Justification: observables
  Version 2.0 is ready to ship

  ✔ Evidence    The package announces version 2.0          # version
  ✔ Evidence    The release runs where commands are found  # environment
  ✔ Strategy    Every release gate passes                  # gates
  ✔ Conclusion  Version 2.0 is ready to ship               # ready

4 elements (4 passed)
verdict: pass
```

## What can be observed

| In `observes` | Observes | The parameter receives |
|---|---|---|
| `"CHANGELOG.md"`, or `File("CHANGELOG.md")` | a file | a `Path` |
| `"build/reports/*.xml"`, or `File(...)` | the files a glob matches | their sorted `list[Path]` |
| `JsonValue("package.json", "/version")` | a value in a JSON file | the value |
| `Env("CI")` | an environment variable | its value, a string |
| an instance of your own `Observable` | what it reaches | what it returns |

`File`, `JsonValue`, `Env` and `Observable` are imported from `jpipe_runner`. A string is
a `File`: the two spellings are the same declaration.

Three rules hold for all of them:

- **Only evidence observes.** A strategy that needs a file has an evidence below it that
  reads the file and produces what the strategy judges.
- **Every evidence observes something.** One that observes nothing checks nothing in the
  world, and validation refuses it (`JP018`).
- **Nothing observed is optional.** If one thing an evidence observes cannot be reached,
  the evidence fails with `JP019` and its step is not called. A check that a file is
  *absent* does not declare that file.

## What a path is relative to

**A path is relative to the file that declares the step**, as a link in a Markdown page is
relative to the page. In the example, `checks/steps.py` reaches `mock/package.json` with
`"../mock/package.json"`. The library therefore observes the same files wherever the
command is typed: from the project's directory as above, from `checks/`, or from anywhere
with the full path of the library.

The report, the messages and the paths a step receives name each file **relative to the
directory the command runs in**, which is the name a changed file has in `git diff`. Run
from the project's directory, `"../mock/package.json"` is reported as `mock/package.json`.

- An absolute path is refused when the library is imported: the library must work on every
  machine.
- A path names a file, never a directory: `"src/"` is refused, with the glob to write
  instead, `"src/**/*"`.
- `.` and `..` are resolved as text. A `..` after a wildcard is refused, since what it
  names would depend on the directories the glob finds.
- A step typed at a Python prompt has no file: its paths are relative to the working
  directory.

### Globs

A path that holds `*`, `?` or `[` is a glob. It designates regular files only, and the
step receives them sorted.

| Pattern | Designates |
|---|---|
| `*` | any run of characters in one name: `build/*.xml` does not reach `build/old/a.xml` |
| `?`, `[ab]` | one character; one of the characters listed |
| `**` | any number of directories, none included: `docs/**/*.md` reaches `docs/a.md` and `docs/x/y/b.md` |
| a trailing `**` | every file below: `src/**` is `src/**/*` |

Matching is case sensitive, and a name that starts with `.` is matched like any other.
`**` is a whole part of a path: `build/**.xml` is refused. A glob that matches no file is
unreachable. `jpipe-runner impact` and `jpipe-runner status` match a glob exactly as a run
does.

## The built-in observables

### `File`

`File(path)` observes one file, or the files a glob matches. The runner reads each file
once, just before the step is called, and records its path, its SHA-256 and its size: the
record is what the step is about to see. Symbolic links are followed.

Unreachable: a file that does not exist or cannot be read, a broken link, a directory, a
pipe or a device, a glob that matches nothing.

### `JsonValue`

`JsonValue(path, pointer)` observes one value in a JSON file. `pointer` is a
[JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901): `"/version"`,
`"/authors/0/name"`; `~1` writes a `/` in a key, and `~0` a `~`. Without a pointer, the
value is the whole document. `path` names one file, not a glob.

The runner records the file, as for a `File`, and the value it found there. A change to
the file reaches the evidence, whether or not the value changed.

Unreachable: whatever makes the file unreachable, a file that is not JSON, a pointer that
designates nothing.

### `Env`

`Env(name)` observes an environment variable. A variable that is not set is unreachable.

**Its value is hidden unless you say otherwise.** A variable may hold a secret, and a
short secret can be guessed from its SHA-256, so by default the report records only that
the variable was observed. `Env("DEPLOY_STAGE", display=True)` records its value and its
SHA-256. [Hiding has a price](#checking-a-report-later-status), paid when a report is
checked later.

## What the report records

Everything observed is recorded. For each element, the JSON report
([`report-schema.md`](report-schema.md)) has four fields about it: `sources`, everything
the step declares; `observes`, the files those depend on; `artifacts`, each file that was
read; and `observations`, what was observed that is not a file.

The first evidence of the example observed two files. The JSON file carries the value
found in it:

```json
{
  "observes": [
    "mock/package.json",
    "mock/CHANGELOG.md"
  ],
  "sources": [
    "mock/package.json#/version",
    "mock/CHANGELOG.md"
  ],
  "artifacts": [
    {
      "path": "mock/package.json",
      "declared": "mock/package.json#/version",
      "reachable": true,
      "sha256": "c4d6b52e00e9d1512ee2f73c0d7aff7bf0ca870cf397383b99cb8d887efa8fd6",
      "size": 44,
      "value": {
        "value": "2.0"
      }
    },
    {
      "path": "mock/CHANGELOG.md",
      "declared": "mock/CHANGELOG.md",
      "reachable": true,
      "sha256": "d0c71b251a7784514e7bf619987b1a76356b195f1849e7b850139ed9a82d709f",
      "size": 17
    }
  ],
  "observations": []
}
```

The second observed a variable, hidden:

```json
{
  "observes": [],
  "sources": [
    "env:PATH"
  ],
  "artifacts": [],
  "observations": [
    {
      "declared": "env:PATH",
      "variable": "PATH",
      "reachable": true,
      "hidden": true,
      "sha256": null,
      "value": null
    }
  ]
}
```

A reachable observation always has a `sha256`, or is `hidden`: there is no third case, so
a report never passes over something its verdict rests on. In a dry run nothing is
observed, and only `sources` and `observes` are filled.

## Which evidence a change reaches: `impact`

[`jpipe-runner impact`](cli.md#impact-analysis) lists the evidence a change to a file
reaches, and everything above it. It follows files: a `File`, the file of a `JsonValue`,
and the files an observable of your own names in `depends_on`.

```console
$ jpipe-runner impact --library checks/steps.py --changed mock/package.json justification.json
Justification: observables

Changed files, and the evidence that observes them:
  mock/package.json  version

Affected (3 elements):
  Evidence    The package announces version 2.0  # version
  Strategy    Every release gate passes          # gates
  Conclusion  Version 2.0 is ready to ship       # ready
```

A change to an environment variable is not a change to a file: `impact` does not see it.

## Checking a report later: `status`

[`jpipe-runner status`](cli.md#staleness) reads the report of an earlier run and says
whether it still holds, without running a step or importing a library. It works from what
the report recorded:

| The run observed | `status` |
|---|---|
| a file | reads it again, and compares its SHA-256 |
| a value in a JSON file | compares the file |
| an environment variable, with `display=True` | reads it again, and compares the SHA-256 of its value |
| anything hidden | cannot compare it: says that a new run is needed |
| what an observable of yours reached, that is neither a file nor a variable | cannot look again: says that a new run is needed |

`status` answers for everything the run observed, or does not answer. The example
observes `PATH` without showing it, so its report cannot be confirmed:

```console
$ jpipe-runner status report.json
Justification: observables

Information was hidden from the report, so it needs a new run:
  env:PATH  environment

Not confirmed (3 elements):
  Evidence    The release runs where commands are found  # environment
  Strategy    Every release gate passes                  # gates
  Conclusion  Version 2.0 is ready to ship               # ready
$ echo $?
1
```

Hiding a value is choosing to run again. Show the variables that hold no secret, and
`status` checks them.

## Writing your own observable

To observe what the runner has no class for, derive `Observable`. It has three methods:

| Method | Says |
|---|---|
| `describe(context)` | how the report names it, in `sources` |
| `observe(context)` | what it is now, as a `Sighting`: the value the step receives, and what the report records |
| `depends_on(context)` | the files a change to which reaches it, for `impact`; none unless you say so |

`context` is where the observation is made from. `context.shown(path)` turns a path
relative to the file that declares the step into the one the report shows.

### Something that is not a file

```python
import socket
from dataclasses import dataclass

from jpipe_runner import Context, Observable, Sighting


@dataclass(frozen=True)
class Host(Observable):
    """The address a host name resolves to."""

    name: str

    def describe(self, context: Context) -> str:
        return f"host:{self.name}"

    def observe(self, context: Context) -> Sighting:
        try:
            address = socket.gethostbyname(self.name)
        except OSError as error:
            return Sighting.unreachable(
                self.describe(context), f"the host {self.name!r}", f"does not resolve: {error}"
            )
        return Sighting.of(self.describe(context), address)


@evidence("dns", observes={"address": Host("localhost")}, produces=["resolves"])
def the_host_resolves(address: str) -> Outcome:
    return Pass(resolves=address.startswith("127."))


here = Context(Path(), Path())
assert Host("localhost").describe(here) == "host:localhost"
assert Host("localhost").observe(here).value.startswith("127.")
```

- `Sighting.of(declared, value)` passes `value` to the step, and records it with its
  SHA-256. `Sighting.of(declared, value, display=False)` hides both.
- `Sighting.unreachable(declared, what, problem)` says that nothing could be observed:
  the evidence fails with `JP019`, "`what`, observed as `address`, `problem`", and the
  step is not called.
- A report that holds what `Host` observed cannot be confirmed by `status`: only `Host`
  can look again.

### Something read in a file

An observable that reads a file can lean on `File`, which reaches the file, records it,
and tells `impact` about it. The report then holds a file, and `status` checks it:

```python
import tomllib
from dataclasses import replace

from jpipe_runner import File


@dataclass(frozen=True)
class TomlValue(Observable):
    """A value of the first table of a TOML file."""

    path: str
    key: str

    def describe(self, context: Context) -> str:
        return f"{context.shown(self.path)}#{self.key}"

    def depends_on(self, context: Context) -> tuple[str, ...]:
        return File(self.path).depends_on(context)

    def observe(self, context: Context) -> Sighting:
        read = File(self.path).observe(context)
        seen = tuple(replace(o, declared=self.describe(context)) for o in read.observations)
        if not all(observation.reachable for observation in seen):
            return Sighting(None, seen)
        document = tomllib.loads(read.value.read_text(encoding="utf-8"))
        return Sighting(document[self.key], seen)
```

Tested as any class is, with a `Context` on a directory of its own:

```python
import tempfile

with tempfile.TemporaryDirectory() as directory:
    project = Path(directory)
    (project / "lib").mkdir()
    (project / "settings.toml").write_text('stage = "production"\n', encoding="utf-8")
    declared_in_lib = Context(project / "lib", project)
    stage = TomlValue("../settings.toml", "stage")

    sighting = stage.observe(declared_in_lib)

    assert sighting.value == "production"
    assert stage.describe(declared_in_lib) == "settings.toml#stage"
    assert stage.depends_on(declared_in_lib) == ("settings.toml",)
    assert [o.path for o in sighting.observations] == ["settings.toml"]
```

### The rules an observable follows

- **It holds what designates the thing, never the thing**: a path, a name. It is created
  when the library is imported, and observed at every run.
- **It can be hashed**, as a frozen dataclass can. One that cannot is refused when the
  library is imported.
- **It records what it observes.** A `Sighting` holds at least one observation, and each
  holds the SHA-256 of what was seen or says that it is hidden. The classes refuse
  anything else, so an observable cannot observe off the record.
- **It describes itself the same way at every run**, so that two reports can be compared.
- **It raises nothing.** An exception in `observe`, such as the `KeyError` of a missing
  key in `TomlValue`, does not stop the run: the evidence fails with `JP019`, which names
  the exception. Return `Sighting.unreachable` to say what is wrong in your own words.

## Testing a step

A step is a plain function, and what it observes is an argument. A test passes its own,
without the runner:

```python
with tempfile.TemporaryDirectory() as directory:
    changelog = Path(directory) / "CHANGELOG.md"
    changelog.write_text("## 2.0\n", encoding="utf-8")

    assert the_package_announces_the_version("2.0", changelog) == Pass(announced=True)
    assert the_package_announces_the_version("2.1", changelog) == Pass(announced=False)

assert commands_are_found("/usr/bin") == Pass(commands_found=True)
```

## When something cannot be observed

Each thing that could not be reached is reported with `JP019`, about the evidence that
observes it; all of them are reported, not only the first. The message names what was
looked for, as the report shows it, and the parameter it was for. The commonest cause is a
path written from the wrong directory: see
[Every evidence fails: its file does not exist](troubleshooting.md#every-evidence-fails-its-file-does-not-exist).
To check a library before the files exist, use `--dry-run`, which observes nothing.
