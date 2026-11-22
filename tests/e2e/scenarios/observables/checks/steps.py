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
