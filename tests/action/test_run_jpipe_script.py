"""
Integration tests for the GitHub Action helper script ``script/action/run_jpipe.sh``.

These tests exercise the argument-building logic of the script directly, without a
real GitHub runner, by pointing ``PYTHON_EXEC_PATH`` at a stub interpreter that
records the exact ``argv`` it receives. They lock in the behaviour introduced when
the command construction was moved from an ``eval``-ed string to a bash array:

* input values are passed to jpipe-runner as literal ``argv`` entries, preserving
  spaces and shell metacharacters; and
* a value containing shell syntax cannot inject or execute anything (regression
  guard against reintroducing ``eval``).
"""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "script" / "action" / "run_jpipe.sh"

# A stub interpreter. It is invoked as ``<stub> -m jpipe_runner <jd> <flags...>``.
# It writes each received argument on its own line to $ARGV_CAPTURE and creates a
# fake diagram in the requested --output-path so the script's "find diagram" step
# succeeds and reports result=0.
STUB = """#!/usr/bin/env bash
: > "$ARGV_CAPTURE"
outdir=""
fmt="svg"
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  printf '%s\\n' "${args[$i]}" >> "$ARGV_CAPTURE"
  case "${args[$i]}" in
    --output-path) outdir="${args[$((i + 1))]}" ;;
    --format) fmt="${args[$((i + 1))]}" ;;
  esac
done
for name in ${STUB_DIAGRAMS:-diagram}; do
  [[ -n "$outdir" ]] && : > "${outdir%/}/${name}.${fmt}"
done
exit 0
"""


class TestRunJpipeScript(unittest.TestCase):
    """Argument-safety tests for run_jpipe.sh."""

    # A value that, under the previous ``eval`` implementation, would break out of
    # quoting and execute ``touch INJECTED``.
    INJECTION_PAYLOAD = "evil:1'; touch INJECTED #"

    def setUp(self):
        self.assertTrue(SCRIPT.exists(), f"script not found: {SCRIPT}")

        tmp_ctx = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_ctx.cleanup)
        self.tmp = Path(tmp_ctx.name)
        self.out_dir = self.tmp / "out"
        self.out_dir.mkdir()
        self.argv_capture = self.tmp / "argv.txt"
        self.github_output = self.tmp / "github_output.txt"
        self.github_output.touch()

        self.stub = self.tmp / "fakepython"
        self.stub.write_text(STUB)
        self.stub.chmod(self.stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    def _outputs(self):
        """Parse the key=value pairs the script wrote to $GITHUB_OUTPUT."""
        out = {}
        for line in self.github_output.read_text().splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                out.setdefault(key, value)
        return out

    def _run(self, *, variable="", diagram=None, diagrams=None, commit_sha="testsha"):
        env = {
            **os.environ,
            "PYTHON_EXEC_PATH": str(self.stub),
            "JD_FILE": "my file.json",  # space on purpose
            "VARIABLE": variable,
            "FORMAT": "svg",
            "OUTPUT_DIR": str(self.out_dir) + "/",
            "GITHUB_OUTPUT": str(self.github_output),
            "COMMIT_SHA": commit_sha,
            "ARGV_CAPTURE": str(self.argv_capture),
        }
        if diagrams is not None:
            # Space-separated basenames the stub should emit (without extension).
            env["STUB_DIAGRAMS"] = " ".join(diagrams)
        if diagram is not None:
            env["DIAGRAM"] = diagram
        proc = subprocess.run(
            ["bash", str(SCRIPT)],
            env=env,
            cwd=self.tmp,
            capture_output=True,
            text=True,
        )
        argv = (
            self.argv_capture.read_text().splitlines()
            if self.argv_capture.exists()
            else []
        )
        return proc, argv

    def test_arguments_passed_intact(self):
        """Spaces and multiple --variable lines survive as distinct argv entries."""
        proc, argv = self._run(variable="user_name:Alice\nteam:The A Team")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        # The JD file with a space is a single argv entry.
        self.assertIn("my file.json", argv)
        # Each variable line becomes its own "--variable <value>" pair.
        self.assertEqual(argv.count("--variable"), 2)
        self.assertIn("user_name:Alice", argv)
        self.assertIn("team:The A Team", argv)
        # Standard flags are forwarded.
        self.assertIn("--output-path", argv)
        self.assertIn("--format", argv)
        self.assertIn("svg", argv)
        # Success is reported to GitHub outputs.
        self.assertIn("result=0", self.github_output.read_text())

    def test_shell_metacharacters_do_not_inject(self):
        """A quote/semicolon-laden value is passed literally and never executed."""
        proc, argv = self._run(variable=self.INJECTION_PAYLOAD)

        self.assertEqual(proc.returncode, 0, proc.stderr)
        # The payload arrives as one literal argv entry...
        self.assertIn(self.INJECTION_PAYLOAD, argv)
        # ...and nothing executed the embedded `touch INJECTED`.
        self.assertFalse((self.tmp / "INJECTED").exists(), "command injection occurred")
        self.assertFalse((REPO_ROOT / "INJECTED").exists(), "command injection occurred")

    def test_glob_diagram_is_not_expanded_by_the_shell(self):
        """`--diagram *` must reach jpipe-runner as a literal asterisk.

        The pattern is matched against diagram names *inside the .jd.json file*, so
        letting the shell expand it against the working directory would silently pass
        filenames instead. `*` is the default value of the Action's `diagram` input,
        so this is the common path, not an edge case.
        """
        # The script runs with cwd=self.tmp, which already holds several entries a
        # glob would expand to. Assert that precondition so the test cannot silently
        # become vacuous.
        cwd_entries = sorted(p.name for p in self.tmp.iterdir())
        self.assertTrue(
            cwd_entries, "cwd must contain files for the glob check to be meaningful"
        )

        proc, argv = self._run(diagram="*")

        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--diagram", argv)
        # The value following --diagram is the literal asterisk...
        self.assertEqual(argv[argv.index("--diagram") + 1], "*")
        # ...and no working-directory entry leaked in via expansion.
        for name in cwd_entries:
            self.assertNotIn(name, argv, f"glob expanded to {name!r}")

    def test_every_generated_diagram_is_kept(self):
        """A wildcard pattern can yield several diagrams; none may be dropped.

        Regression guard: the script used to keep only `find ... | head -n1`, so
        with the default `--diagram '*'` all but one diagram were silently
        discarded -- and which one survived depended on directory order.
        """
        proc, _ = self._run(diagram="*", diagrams=["catalogue", "release"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

        out = self._outputs()
        self.assertEqual(out["diagram_count"], "2")

        kept = sorted(p.name for p in Path(out["diagram_dir"]).iterdir())
        self.assertEqual(kept, ["catalogue_testsha.svg", "release_testsha.svg"])

        # The primary diagram is deterministic (sorted), not directory-order luck.
        self.assertEqual(out["diagram_name"], "catalogue_testsha.svg")

    def test_missing_commit_sha_does_not_leave_a_dangling_underscore(self):
        """COMMIT_SHA is empty on non-PR events; the name must not become `x_.svg`.

        `github.event.pull_request.head.sha` is empty for workflow_dispatch/push,
        which produced artifacts literally named "catalogue_.svg".
        """
        proc, _ = self._run(diagrams=["catalogue"], commit_sha="")
        self.assertEqual(proc.returncode, 0, proc.stderr)

        out = self._outputs()
        self.assertEqual(out["diagram_name"], "catalogue.svg")
        self.assertNotIn("_.svg", out["diagram_name"])

    def test_only_top_level_diagrams_are_collected(self):
        """Files nested under OUTPUT_DIR must be ignored.

        OUTPUT_DIR defaults to the runner workspace, which also contains the
        checked-out repository, so a recursive search could pick up unrelated
        images from the project itself.
        """
        nested = self.out_dir / "checkout" / "docs"
        nested.mkdir(parents=True)
        (nested / "unrelated.svg").write_text("not a generated diagram")

        proc, _ = self._run(diagrams=["catalogue"])
        self.assertEqual(proc.returncode, 0, proc.stderr)

        out = self._outputs()
        self.assertEqual(out["diagram_count"], "1")
        kept = [p.name for p in Path(out["diagram_dir"]).iterdir()]
        self.assertNotIn("unrelated.svg", kept)
        self.assertTrue((nested / "unrelated.svg").exists(), "unrelated file was moved")

    def test_runner_exit_code_survives_when_no_diagram_is_produced(self):
        """A failing runner keeps its own exit code even if no diagram appears.

        The no-diagram branch used to hard-code `result=1`, masking the real
        failure (e.g. exit 2) and making the final "Fail if jPipe Runner failed"
        step exit with the wrong code. The captured output must also be reported,
        since this is precisely when the user needs the diagnostic.
        """
        # Stub that fails with a distinctive code and writes no diagram at all.
        failing = self.tmp / "failingpython"
        failing.write_text(
            '#!/usr/bin/env bash\n: > "$ARGV_CAPTURE"\n'
            'echo "boom: something went wrong"\nexit 2\n'
        )
        failing.chmod(failing.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        env = {
            **os.environ,
            "PYTHON_EXEC_PATH": str(failing),
            "JD_FILE": "my file.json",
            "VARIABLE": "",
            "FORMAT": "svg",
            "OUTPUT_DIR": str(self.out_dir) + "/",
            "GITHUB_OUTPUT": str(self.github_output),
            "COMMIT_SHA": "testsha",
            "ARGV_CAPTURE": str(self.argv_capture),
        }
        subprocess.run(
            ["bash", str(SCRIPT)], env=env, cwd=self.tmp, capture_output=True, text=True
        )

        out = self._outputs()
        self.assertEqual(out["result"], "2", "runner exit code was masked")
        self.assertIn("boom: something went wrong", self.github_output.read_text())


if __name__ == "__main__":
    unittest.main()
