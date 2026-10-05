"""Layer 2: every scenario's whole JSON report against its golden file (tests/README.md)."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.golden import assert_matches_golden, normalise
from tests.scenarios import EXIT_CODES, GOLDEN_FILE, Scenario, discover

# The scenarios drive the CLI, which arrives with M6. Until then they are collected and
# skipped, and they start running, with no edit here, once `python -m jpipe_runner` exists.
CLI_AVAILABLE = importlib.util.find_spec("jpipe_runner.__main__") is not None


@pytest.mark.skipif(not CLI_AVAILABLE, reason="needs the CLI (`python -m jpipe_runner`, #124)")
@pytest.mark.parametrize("scenario", discover(), ids=lambda scenario: scenario.name)
def test_scenario(scenario: Scenario, tmp_path: Path, update_goldens: bool) -> None:
    workdir = tmp_path / scenario.name
    shutil.copytree(
        scenario.directory,
        workdir,
        ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
    )
    result = subprocess.run(
        scenario.command(),
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == scenario.exit_code, (
        f"expected exit {scenario.exit_code} ({EXIT_CODES[scenario.exit_code]}), "
        f"got {result.returncode}\n--- stderr\n{result.stderr}"
    )
    # tmp_path may sit behind a symlink (macOS: /var -> /private/var); hide both spellings.
    paths = {str(workdir): "<scenario>", str(workdir.resolve()): "<scenario>"}
    report = normalise(json.loads(result.stdout), paths)
    assert_matches_golden(report, scenario.golden, update=update_goldens)
