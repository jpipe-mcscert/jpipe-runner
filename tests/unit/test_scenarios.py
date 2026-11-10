from pathlib import Path

import pytest

from tests.scenarios import JUSTIFICATION_FILE, SCENARIO_FILE, ScenarioError, load

VALID = """
description = "A passing run."
origin = "new in v4"
libraries = ["steps.py"]
exit_code = 0
"""


def make(tmp_path: Path, toml: str = VALID, files: tuple[str, ...] = ("steps.py",)) -> Path:
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / SCENARIO_FILE).write_text(toml, encoding="utf-8")
    (directory / JUSTIFICATION_FILE).write_text("{}", encoding="utf-8")
    for name in files:
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        (directory / name).touch()
    return directory


def test_load_reads_a_valid_scenario(tmp_path: Path) -> None:
    scenario = load(make(tmp_path))
    assert scenario.name == "demo"
    assert scenario.libraries == ("steps.py",)
    assert scenario.python_path == ()
    assert scenario.command()[1:] == [
        "-m",
        "jpipe_runner",
        "--json",
        "--library",
        "steps.py",
        JUSTIFICATION_FILE,
    ]


def test_command_passes_libraries_and_python_path_in_order(tmp_path: Path) -> None:
    toml = VALID.replace('["steps.py"]', '["steps/*.py", "extra.py"]') + 'python_path = ["lib"]\n'
    directory = make(tmp_path, toml, files=("steps/a.py", "extra.py", "lib/__init__.py"))
    command = load(directory).command()
    assert command[command.index("--json") :] == [
        "--json",
        "--library",
        "steps/*.py",
        "--library",
        "extra.py",
        "--python-path",
        "lib",
        JUSTIFICATION_FILE,
    ]


@pytest.mark.parametrize(
    ("toml", "error"),
    [
        pytest.param(VALID + "colour = 1\n", "unknown keys", id="unknown-key"),
        pytest.param(VALID.replace("exit_code = 0\n", ""), "missing keys", id="missing-key"),
        pytest.param(VALID.replace("exit_code = 0", "exit_code = 2"), "exit_code", id="usage-exit"),
        pytest.param(
            VALID.replace("exit_code = 0", "exit_code = true"), "exit_code", id="bool-exit"
        ),
        pytest.param(VALID.replace('["steps.py"]', '"steps.py"'), "libraries", id="not-a-list"),
        pytest.param(VALID.replace('["steps.py"]', "[]"), "at least one", id="no-library"),
        pytest.param(
            VALID.replace('["steps.py"]', '["nope.py"]'), "matches no file", id="no-match"
        ),
        pytest.param(VALID + 'python_path = ["lib"]\n', "not a directory", id="bad-path"),
        pytest.param(VALID + "exercises = [1]\n", "list of strings", id="bad-item"),
        pytest.param("description = ", "scenario.toml", id="bad-toml"),
    ],
)
def test_load_rejects_malformed_scenarios(tmp_path: Path, toml: str, error: str) -> None:
    directory = make(tmp_path, toml)
    with pytest.raises(ScenarioError, match=error):
        load(directory)


def test_load_requires_the_justification(tmp_path: Path) -> None:
    directory = make(tmp_path)
    (directory / JUSTIFICATION_FILE).unlink()
    with pytest.raises(ScenarioError, match=JUSTIFICATION_FILE):
        load(directory)
