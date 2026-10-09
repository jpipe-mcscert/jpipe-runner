"""The command line as a process: the installed script, ``python -m``, and git (#124, #146).

``tests/unit/test_cli.py`` runs the command in process; these run it as a user does, for
what only a process shows: the script that installing the package creates, the
``sys.path`` each way of starting it gets, and git.
"""

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.scenarios import GOLDEN_FILE, SCENARIOS_ROOT

SCRIPT = Path(sys.executable).parent / "jpipe-runner"
STARTS = {
    "script": [str(SCRIPT)],
    "python -m": [sys.executable, "-m", "jpipe_runner"],
}
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


@pytest.fixture
def release(tmp_path: Path) -> Path:
    workdir = tmp_path / "release_example"
    shutil.copytree(
        SCENARIOS_ROOT / "release_example",
        workdir,
        ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
    )
    return workdir


def _runner(start: list[str], cwd: Path) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(*arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*start, *arguments], cwd=cwd, capture_output=True, text=True, timeout=60, check=False
        )

    return run


def test_installing_the_package_creates_the_script() -> None:
    assert SCRIPT.is_file()


def test_the_script_and_python_m_give_the_same_report(release: Path) -> None:
    arguments = ("--json", "--library", "steps.py", "justification.json")
    script = _runner(STARTS["script"], release)(*arguments)
    module = _runner(STARTS["python -m"], release)(*arguments)

    assert (script.returncode, script.stdout) == (module.returncode, module.stdout)
    assert script.returncode == 0
    assert '"verdict": "pass"' in script.stdout


@pytest.mark.parametrize("start", STARTS.values(), ids=STARTS.keys())
def test_a_module_beside_the_library_is_imported_only_through_the_python_path(
    start: list[str], release: Path
) -> None:
    (release / "helper.py").write_text("RELEASE = '2.0'\n", encoding="utf-8")
    steps = release / "steps.py"
    steps.write_text(
        steps.read_text(encoding="utf-8").replace('RELEASE = "2.0"', "from helper import RELEASE"),
        encoding="utf-8",
    )
    run = _runner(start, release)

    without = run("--library", "steps.py", "justification.json")
    with_path = run("--library", "steps.py", "--python-path", ".", "justification.json")

    assert without.returncode == 3
    assert "JP020 error: steps.py cannot be imported: ModuleNotFoundError" in without.stdout
    assert with_path.returncode == 0


@pytest.mark.parametrize("start", STARTS.values(), ids=STARTS.keys())
def test_a_module_of_the_working_directory_does_not_shadow_the_runners_dependencies(
    start: list[str], release: Path
) -> None:
    for dependency in ("networkx", "jsonschema"):
        (release / f"{dependency}.py").write_text(
            "raise ImportError('shadowed')\n", encoding="utf-8"
        )

    done = _runner(start, release)("--library", "steps.py", "justification.json")

    assert done.returncode == 0, done.stderr


def test_importing_the_package_loads_none_of_its_dependencies() -> None:
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, jpipe_runner; print(sorted({'networkx', 'jsonschema'} & set(sys.modules)))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert done.stdout == "[]\n"


@needs_git
def test_impact_since_a_revision_reads_what_git_says_changed(release: Path) -> None:
    def git(*arguments: str) -> None:
        identity = ["-c", "user.name=jpipe", "-c", "user.email=jpipe@example.org"]
        subprocess.run(["git", *identity, *arguments], cwd=release, check=True, capture_output=True)

    (release / ".gitignore").write_text("__pycache__/\nreport.json\n", encoding="utf-8")
    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "release")
    (release / "mock" / "CHANGELOG.md").write_text("2.1\n", encoding="utf-8")

    done = _runner(STARTS["script"], release)(
        "impact", "--library", "steps.py", "--since", "HEAD", "justification.json"
    )

    assert done.returncode == 0
    assert "  mock/CHANGELOG.md  release:e2\n" in done.stdout
    assert "# release:c\n" in done.stdout
