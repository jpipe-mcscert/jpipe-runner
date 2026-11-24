"""Layer 2: every scenario's whole JSON report against its golden file (tests/README.md)."""

import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.golden import assert_matches_golden, normalize
from tests.scenarios import EXIT_CODES, GOLDEN_FILE, Scenario, discover

# The scenarios drive the CLI, which arrives with M6. Until then they are collected and
# skipped, and they start running, with no edit here, once `python -m jpipe_runner` exists.
CLI_AVAILABLE = importlib.util.find_spec("jpipe_runner.__main__") is not None


@pytest.mark.skipif(not CLI_AVAILABLE, reason="needs the CLI (`python -m jpipe_runner`, #124)")
@pytest.mark.parametrize("jobs", [None, "4"], ids=["one-job", "four-jobs"])
@pytest.mark.parametrize("scenario", discover(), ids=lambda scenario: scenario.name)
def test_scenario(
    scenario: Scenario, jobs: str | None, tmp_path: Path, update_goldens: bool
) -> None:
    # Four jobs give the same report as one, the default, which writes the golden file.
    workdir = tmp_path / scenario.name
    shutil.copytree(
        scenario.directory,
        workdir,
        ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
    )
    command = scenario.command()
    if jobs is not None:
        command[-1:-1] = ["--jobs", jobs]
    result = subprocess.run(
        command,
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
    report = normalize(json.loads(result.stdout), paths)
    assert_matches_golden(report, scenario.golden, update=update_goldens and jobs is None)


@pytest.mark.skipif(not CLI_AVAILABLE, reason="needs the CLI (`python -m jpipe_runner`, #124)")
@pytest.mark.parametrize("scenario", discover(), ids=lambda scenario: scenario.name)
def test_an_incremental_run_with_nothing_changed_reports_what_its_baseline_did(
    scenario: Scenario, tmp_path: Path
) -> None:
    # The golden report is the baseline (ADR-0039): nothing changed, so what can be reused
    # is, and the report is the golden one, but for what says so.
    workdir = tmp_path / scenario.name
    shutil.copytree(
        scenario.directory,
        workdir,
        ignore=shutil.ignore_patterns(GOLDEN_FILE, "__pycache__"),
    )
    golden = json.loads(scenario.golden.read_text(encoding="utf-8"))
    (workdir.parent / "baseline.json").write_text(json.dumps(golden), encoding="utf-8")
    command = scenario.command()
    command[-1:-1] = ["--incremental", "../baseline.json"]

    result = subprocess.run(
        command, cwd=workdir, capture_output=True, text=True, timeout=60, check=False
    )

    assert result.returncode == scenario.exit_code, result.stderr
    paths = {str(workdir): "<scenario>", str(workdir.resolve()): "<scenario>"}
    report = normalize(json.loads(result.stdout), paths)
    selection = report.pop("selection")
    if golden["verdict"] in ("pass", "fail", "skip"):
        assert selection["baseline"] == "../baseline.json"
        # Only what failed, or what the report cannot check again, runs again: a hidden
        # value, or one only its library can observe.
        assert all(
            why == "it failed in the baseline"
            or "cannot be checked again" in why
            or " runs again" in why
            for why in selection["rerun"].values()
        ), selection["rerun"]
    for element in report["elements"]:
        reused = selection is not None and element["id"] not in selection["rerun"]
        assert element.pop("reused") is reused
    for element in golden["elements"]:
        element.pop("reused")
    golden.pop("selection")
    assert report == golden
