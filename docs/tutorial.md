# Tutorial: from a `.jd` file to a green run

This tutorial takes an argument written in jPipe to a run that checks it, on one page. It
uses the release argument of the [jPipe tutorials](https://www.jpipe.org/tutorials/): a
team argues that version 2.0 is ready to ship. You will write the argument, compile it,
write a Python function for each check it relies on, and run them with `jpipe-runner`.
Every file you need is on this page.

[`end-to-end.md`](end-to-end.md) follows the same example in more depth, stage by stage;
this page is the short way through.

## 1. Install

`jpipe-runner` needs Python 3.11 or later. Install it in a virtual environment, beside the
packages your checks will import:

```shell
python3 -m venv .venv
. .venv/bin/activate
pip install jpipe-runner
```

Until version 4.0.0 is released, `pip install jpipe-runner` installs version 3, which this
page does not describe: install version 4 from its repository instead, with
`pip install git+https://github.com/jpipe-mcscert/jpipe-runner`.

You will also need the [jPipe compiler](https://www.jpipe.org/) to compile your own
arguments; for this one, step 3 gives you the result. Drawing diagrams needs
[Graphviz](https://graphviz.org/download/); this tutorial does not.

## 2. Write the argument

A justification states a claim, the reasoning that supports it, and the evidence the
reasoning rests on. Save this as `release.jd`:

```text
justification release {
  // The claim we want to establish
  conclusion c is "Version 2.0 is ready to ship"

  // The reasoning that connects evidence to the conclusion
  strategy s is "All release gates pass"
  s supports c

  // The supporting evidence (grounds)
  evidence e1 is "The test suite passes"
  e1 supports s

  evidence e2 is "The changelog is up to date"
  e2 supports s
}
```

Two pieces of evidence support a strategy, which supports the conclusion. On paper, the
argument is only as good as the reader's trust in its evidence. The runner backs each piece
of evidence, and the strategy, with a check that is actually run.

## 3. Compile it

`jpipe-runner` does not read `.jd` files: the jPipe compiler compiles them to JSON.

```shell
jpipe process -i release.jd -m release -f JSON -o justification.json
```

Without the compiler, save this as `justification.json`: it is what the compiler writes.

```json
{
  "elements": [
    {
      "escaped": "version_2_0_is_ready_to_ship",
      "id": "release:c",
      "label": "Version 2.0 is ready to ship",
      "type": "conclusion"
    },
    {
      "escaped": "all_release_gates_pass",
      "id": "release:s",
      "label": "All release gates pass",
      "type": "strategy"
    },
    {
      "escaped": "the_test_suite_passes",
      "id": "release:e1",
      "label": "The test suite passes",
      "type": "evidence"
    },
    {
      "escaped": "the_changelog_is_up_to_date",
      "id": "release:e2",
      "label": "The changelog is up to date",
      "type": "evidence"
    }
  ],
  "name": "release",
  "type": "justification",
  "relations": [
    {
      "source": "release:s",
      "target": "release:c"
    },
    {
      "source": "release:e1",
      "target": "release:s"
    },
    {
      "source": "release:e2",
      "target": "release:s"
    }
  ]
}
```

Each element's `id` is its name in the `.jd` file, qualified by the justification's:
`e1` is `release:e1`. Your checks will name the elements by these ids.

The compiler can also write the skeleton of a step library (`-f PYTHON`), but as of jPipe
2.5.0 that skeleton targets `jpipe-runner` 3
([#140](https://github.com/jpipe-mcscert/jpipe-runner/issues/140)): write it by hand, as
below.

## 4. The artifacts the evidence checks

Evidence is about something in the world: here, the test suite's report and the
changelog. In a real project they come from your build; for this tutorial, create them
under `mock/`. Save this as `mock/junit.xml`, a test report with no failure:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="release" tests="42" failures="0" errors="0" skipped="0">
  <testcase classname="release" name="test_release_builds"/>
</testsuite>
```

and this as `mock/CHANGELOG.md`, a changelog that names the release:

```markdown
2.0
```

## 5. Write the checks

A step library is a Python file with one function per element to check. Save this as
`steps.py`:

```python
from pathlib import Path
from xml.etree import ElementTree

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

RELEASE = "2.0"


@evidence("release:e1", observes={"report": "mock/junit.xml"}, produces=["tests_pass"])
def the_test_suite_passes(report: Path) -> Outcome:
    """[evidence] The test suite passes"""
    suite = ElementTree.parse(report).getroot()
    failed = int(suite.get("failures", "0")) + int(suite.get("errors", "0"))
    if failed == 0:
        return Pass(tests_pass=True)
    return Fail(f"{report}: {failed} tests failed")


@evidence("release:e2", observes={"changelog": "mock/CHANGELOG.md"}, produces=["changelog_ok"])
def the_changelog_is_up_to_date(changelog: Path) -> Outcome:
    """[evidence] The changelog is up to date"""
    if RELEASE in changelog.read_text(encoding="utf-8"):
        return Pass(changelog_ok=True)
    return Fail(f"{changelog} does not name release {RELEASE}")


@strategy("release:s", consumes=["tests_pass", "changelog_ok"])
def all_release_gates_pass(tests_pass: bool, changelog_ok: bool) -> Outcome:
    """[strategy] All release gates pass"""
    if tests_pass and changelog_ok:
        return Pass()
    return Fail("a release gate did not pass")
```

- **The decorator says which element a function checks**: `@evidence` for evidence,
  `@strategy` for a strategy, with the element's id.
- **Evidence declares the files it reads** with `observes`, which maps a parameter of the
  function to a path. The runner checks that the file is there, records its SHA-256, and
  passes it to the function as a `Path`.
- **Data flows up the argument**: each evidence `produces` a value, which the strategy
  `consumes`, as a parameter of the same name.
- **A function returns an outcome**: `Pass(...)`, with the values it produces, or
  `Fail(reason)`.
- **The conclusion needs no function**: it holds when what supports it holds.

[`authoring.md`](authoring.md) describes all of it.

## 6. Run it

Your directory now holds `justification.json`, `steps.py` and `mock/`. Run the
justification against the library, from that directory:

```console
$ jpipe-runner --library steps.py justification.json
Justification: release
  Version 2.0 is ready to ship

  ✔ Evidence    The test suite passes         # release:e1
  ✔ Evidence    The changelog is up to date   # release:e2
  ✔ Strategy    All release gates pass        # release:s
  ✔ Conclusion  Version 2.0 is ready to ship  # release:c

4 elements (4 passed)
verdict: pass
$ echo $?
0
```

A green run: every check passed, so the argument holds, and the exit code is 0. In CI,
that is the step that passes.

## 7. When a check does not hold

Edit `mock/junit.xml` to record two failed tests, `failures="2"`, and run again:

```console
$ jpipe-runner --library steps.py justification.json
Justification: release
  Version 2.0 is ready to ship

  ✘ Evidence    The test suite passes         # release:e1
      steps.the_test_suite_passes: mock/junit.xml: 2 tests failed
      observed mock/junit.xml (sha256 f757d068913c…, 187 bytes)
  ✔ Evidence    The changelog is up to date   # release:e2
  - Strategy    All release gates pass        # release:s
      not run: release:e1 did not pass
  - Conclusion  Version 2.0 is ready to ship  # release:c
      not run: release:e1 did not pass

4 elements (1 failed, 2 skipped, 1 passed)
verdict: fail
$ echo $?
1
```

The evidence fails, with the reason its function gave, and the file it read. The strategy
and the conclusion are skipped, not called: they would need `tests_pass`, which the failed
evidence never produced. The exit code is 1: in CI, the step fails. Set `failures="0"`
back before going on.

## 8. Check the library without running it

`--dry-run` checks that the library fits the argument, and calls no function: a check of
the library alone, before the files it reads exist.

```console
$ jpipe-runner --library steps.py --dry-run justification.json
Justification: release
  Version 2.0 is ready to ship

verdict: valid (a dry run: no step was called)
$ echo $?
0
```

Mistakes in the library are reported here, each with a code and a fix: a function bound to
no element, a variable consumed but never produced, an evidence that observes nothing.
[`rules.md`](rules.md) lists every one.

## 9. For CI and for readers

The text report is for people. For a program, `--report report.json` writes the JSON
report, the contract for scripts and the GitHub Action
([`report-schema.md`](report-schema.md)). With Graphviz installed,
`--diagram release.svg` draws the argument with the run's statuses over it, as the jPipe
compiler draws it, and `--dataflow release-dataflow.svg` adds the files and values that
flow through it. [`cli.md`](cli.md) describes every option and exit code, and
`jpipe-runner impact` and `jpipe-runner status`, which tell what a change reaches and what
has changed since a run.

## Going further: composed arguments

Arguments grow by composition. jPipe can `refine` an evidence into a whole sub-argument,
`assemble` arguments under a new strategy, or unify their shared elements. The step
libraries written for each argument keep working on the composed one: no edit needed.

A later draft of the release argument, `draft`, adds a sub-argument for the
documentation, and still treats "the test suite passes" as one piece of evidence. A second
justification, `tested`, argues "the code is tested" in full. `refine` grafts `tested`
onto the draft in place of that evidence:

```text
justification readiness is refine(draft, tested) {
  hook: "tests"
}
```

Each argument has its own library, `draft_steps.py` and `tested_steps.py`
([in the repository](../tests/e2e/scenarios/composed/)), written before the composition.
Run them together against the compiled `readiness`:

```console
$ jpipe-runner --library draft_steps.py --library tested_steps.py justification.json
Justification: readiness
  Version 2.0 is ready to ship

  ✔ Evidence        The changelog is up to date               # readiness:draft:changelog
  ✔ Strategy        The changelog and API docs are current    # readiness:draft:docs
  ✔ Sub-conclusion  The documentation is updated              # readiness:draft:documented
  ✔ Evidence        The test suite passes                     # readiness:tested:suite
  ✔ Evidence        Coverage is above 80%                     # readiness:tested:coverage
  ✔ Strategy        The test suite passes with high coverage  # readiness:tested:testing
  ✔ Sub-conclusion  The code is tested                        # readiness:hook
  ✔ Strategy        All release gates pass                    # readiness:draft:gates
  ✔ Conclusion      Version 2.0 is ready to ship              # readiness:draft:ready

JP008 warning [readiness:hook]: draft_steps.the_test_suite_passes is declared as evidence, and is bound to a sub-conclusion: it runs as a cross-check of the argument below it
  fix: Nothing to do for a cross-check. If the library serves only the composed model, declare the step with @sub_conclusion.

9 elements (9 passed)
1 diagnostic (1 warning)
verdict: pass
$ echo $?
0
```

Three things happened:

- **The ids changed, and the functions still bind.** Composition prefixed each id with the
  composed justification's name: `draft:changelog` became `readiness:draft:changelog`. A
  function names an element by a tail of its id as well as by its full id, so
  `@evidence("draft:changelog")` still binds, as long as no other element's id ends the
  same way. This is how the compiler shortens the ids it writes, too.
- **An element kept its old ids as aliases.** The refined evidence `draft:tests` and the
  conclusion of `tested` became one sub-conclusion, `readiness:hook`, which answers to both
  old ids. The draft's function for "the test suite passes" binds to it, through its alias.
- **That function now runs as a cross-check.** It was written for an evidence, and is bound
  to a sub-conclusion argued in full below it. The runner calls it after that argument,
  and only if it passed, and says so with a warning (`JP008`) rather than an error.

[Libraries written for separate models](authoring.md#libraries-written-for-separate-models)
says what such libraries need when they run together, and
[Binding](authoring.md#binding-how-an-id-designates-an-element) how an id designates an
element.
