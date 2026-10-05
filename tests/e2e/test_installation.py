import subprocess
import sys
import tomllib

from tests.conftest import REPO_ROOT


def test_installed_package_reports_its_version() -> None:
    """A fresh interpreter imports the installed distribution, not a bare source tree."""
    result = subprocess.run(
        [sys.executable, "-c", "import jpipe_runner; print(jpipe_runner.__version__)"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT / "tests",
    )
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert result.stdout.strip() == pyproject["tool"]["poetry"]["version"]
