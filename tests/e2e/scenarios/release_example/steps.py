"""The release example's step library, on the v4 API.

A hand-written port of jpipe-examples/release-example/run/release_lib.py, which the
jPipe tutorials teach. The checks read mock/ instead of a real build: mock/tests.ok
stands for a passing test suite and mock/CHANGELOG.md for the release's changelog.
"""

from pathlib import Path

from jpipe_runner import Fail, Outcome, Pass, evidence, strategy

RELEASE = "2.0"


@evidence("release:e1", produces=["tests_pass"])
def the_test_suite_passes() -> Outcome:
    """[evidence] The test suite passes"""
    if Path("mock/tests.ok").is_file():
        return Pass(tests_pass=True)
    return Fail("mock/tests.ok not found: the test suite did not pass")


@evidence("release:e2", produces=["changelog_ok"])
def the_changelog_is_up_to_date() -> Outcome:
    """[evidence] The changelog is up to date"""
    if RELEASE in Path("mock/CHANGELOG.md").read_text(encoding="utf-8"):
        return Pass(changelog_ok=True)
    return Fail(f"mock/CHANGELOG.md does not name release {RELEASE}")


@strategy("release:s", consumes=["tests_pass", "changelog_ok"])
def all_release_gates_pass(tests_pass: bool, changelog_ok: bool) -> Outcome:
    """[strategy] All release gates pass"""
    if tests_pass and changelog_ok:
        return Pass()
    return Fail("a release gate did not pass")
