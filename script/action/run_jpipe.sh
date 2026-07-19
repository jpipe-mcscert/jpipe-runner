#!/usr/bin/env bash
set +e

###############################################################################
# JPIPE RUNNER EXECUTION SCRIPT
#
# This script executes the jPipe Runner tool (`jpipe_runner`) with configurable
# parameters, collects its output, and renames the generated diagram file to
# include the commit SHA for traceability.
#
# Execution Flow:
#   1. Prepare Python command with optional flags and multi-line parameters.
#   2. Run jpipe_runner and capture both stdout and stderr.
#   3. Search for the generated diagram file in the working directory.
#   4. Rename the diagram file to include the commit SHA.
#   5. Output results to GitHub Actions environment variables.
#
# Required Environment Variables:
#   PYTHON_EXEC_PATH   : Path to Python interpreter (default: "python" if unset)
#   PYTHON_PATH   : Extra folders to search for Python files/modules (--python-path)
#   JD_FILE       : Path to JD (Justification Json Document) file for jPipe
#   VARIABLE      : Multi-line variable definitions for jPipe (--variable)
#   LIBRARY       : Multi-line library imports for jPipe (--library)
#   CONFIG_FILE   : Path to config file for jPipe
#   DIAGRAM       : Diagram name override
#   DRY_RUN       : "true" to enable dry-run mode (no execution)
#   FORMAT        : Diagram output format (default: "svg")
#   COMMIT_SHA    : Commit SHA (used to rename output file)
###############################################################################

# -----------------------------------------------------------------------------
# STEP 1: Initialize variables
# -----------------------------------------------------------------------------
PYTHON_EXEC_PATH="${PYTHON_EXEC_PATH:-python}"
# OUTPUT_DIR defaults to the GitHub-hosted runner workspace but can be overridden
# via the environment (e.g. for local testing).
OUTPUT_DIR="${OUTPUT_DIR:-/home/runner/work/}"

echo "Using Python interpreter at: $PYTHON_EXEC_PATH"

# Base command to run, built as an array so that arbitrary input values
# (quotes, spaces, newlines) are passed as literal argv entries and never
# re-parsed by the shell. This avoids the command injection / quoting issues
# that come with building a string and running it through `eval`.
CMD=("$PYTHON_EXEC_PATH" -m jpipe_runner "${JD_FILE}")

# -----------------------------------------------------------------------------
# STEP 2: Helper functions for appending flags
# -----------------------------------------------------------------------------
append_flag() {
  # Appends a flag with its value if the value is non-empty
  local val="$1"
  local flag="$2"
  [[ -n "$val" ]] && CMD+=("$flag" "$val")
}

handle_multiline_input() {
  # Appends a flag for each non-empty line in multi-line input
  local input="$1"
  local flag="$2"
  while IFS= read -r line; do
    [[ -n "$line" ]] && CMD+=("$flag" "$line")
  done <<< "$input"
}

# -----------------------------------------------------------------------------
# STEP 3: Append command arguments from environment variables
# -----------------------------------------------------------------------------
handle_multiline_input "${VARIABLE:-}" "--variable"
handle_multiline_input "${LIBRARY:-}" "--library"
handle_multiline_input "${PYTHON_PATH:-}" "--python-path"

append_flag "${CONFIG_FILE:-}" "--config-file"
append_flag "${DIAGRAM:-}" "--diagram"

[[ "${DRY_RUN:-false}" == "true" ]] && CMD+=("--dry-run")

CMD+=("--output-path" "$OUTPUT_DIR")
CMD+=("--format" "${FORMAT:-svg}")

# -----------------------------------------------------------------------------
# STEP 4: Run the command and capture output
# -----------------------------------------------------------------------------
# Print a shell-quoted rendering of the command. "${CMD[*]}" would join the
# elements bare, displaying e.g. `--diagram *`, which looks like an unprotected
# glob even though the array is executed safely below. %q escapes each element so
# the log is unambiguous (and copy-pasteable).
printf 'Running:'
printf ' %q' "${CMD[@]}"
printf '\n'
OUTPUT=$("${CMD[@]}" 2>&1)  # Capture both stdout and stderr
RESULT=$?

echo "Command exited with code $RESULT"

# -----------------------------------------------------------------------------
# STEP 5: Locate the generated diagrams
#
# Why:
#   --diagram takes a wildcard (default "*"), so the runner may emit SEVERAL
#   diagrams. Previously only `head -n1` was kept and the rest were silently
#   discarded -- and which one survived depended on directory order.
#
# How:
#   - Search only the TOP LEVEL of OUTPUT_DIR. It defaults to the runner
#     workspace, which also contains the checked-out repository; a recursive
#     search would happily pick up unrelated *.svg files from the project.
#   - Sort the matches so the "primary" diagram is deterministic.
#   - If none found, set result=1 and exit gracefully.
#
# (`while read` rather than `mapfile`: macOS ships bash 3.2, where mapfile does
# not exist, and this script is exercised by the local test-suite.)
# -----------------------------------------------------------------------------
GENERATED=()
while IFS= read -r found; do
  [[ -n "$found" ]] && GENERATED+=("$found")
done < <(find "$OUTPUT_DIR" -maxdepth 1 -name "*.${FORMAT:-svg}" -type f | sort)

if [[ ${#GENERATED[@]} -eq 0 ]]; then
  echo "No diagram file found in $OUTPUT_DIR"
  # Preserve the runner's own exit code. Hard-coding result=1 here masked the real
  # failure reason (e.g. an exit code of 2) and made the final "Fail if jPipe
  # Runner failed" step exit with the wrong code. Only synthesise a failure when
  # the runner itself reported success but produced nothing.
  if [[ "$RESULT" -eq 0 ]]; then
    echo "::warning::jPipe Runner exited 0 but produced no ${FORMAT:-svg} diagram in $OUTPUT_DIR"
    RESULT=1
  fi
  # Emit the captured output too: this is exactly the path where the user most
  # needs the diagnostic, and without it the PR comment showed an empty log.
  {
    echo "result=$RESULT"
    echo "runner_output<<EOF"
    echo "$OUTPUT"
    echo "EOF"
  } >> "$GITHUB_OUTPUT"
  echo "Runner output:"
  echo "$OUTPUT"
  exit 0
fi

# -----------------------------------------------------------------------------
# STEP 6: Rename with the commit SHA and gather into a dedicated folder
#
# Why the SHA:
#   - Prevents overwriting in artifact storage.
#   - Allows traceability back to the commit that generated the diagram.
#
# COMMIT_SHA can legitimately be EMPTY (e.g. a workflow_dispatch run, where
# github.event.pull_request.head.sha does not exist). In that case the suffix is
# omitted entirely instead of leaving a dangling underscore, which used to yield
# nonsense names like "catalogue_.svg".
#
# Why a dedicated folder:
#   The multi-diagram upload targets this directory. OUTPUT_DIR itself is the
#   runner workspace and must NEVER be uploaded wholesale.
#
# Example:
#   mydiagram.svg -> <OUTPUT_DIR>/jpipe-diagrams/mydiagram_<COMMIT_SHA>.svg
# -----------------------------------------------------------------------------
SUFFIX=""
if [[ -n "${COMMIT_SHA:-}" ]]; then
  SUFFIX="_${COMMIT_SHA}"
else
  echo "::warning::COMMIT_SHA is empty; diagram names will not carry a commit suffix."
fi

DIAGRAM_DIR="${OUTPUT_DIR%/}/jpipe-diagrams"
mkdir -p "$DIAGRAM_DIR"

RENAMED=()
for original in "${GENERATED[@]}"; do
  base=$(basename "$original" ."${FORMAT:-svg}")
  target="${DIAGRAM_DIR}/${base}${SUFFIX}.${FORMAT:-svg}"
  # `--` so a diagram whose name begins with "-" is never parsed as an
  # option. Quoting alone does not prevent that.
  mv -- "$original" "$target"
  RENAMED+=("$target")
done

DIAGRAM_COUNT=${#RENAMED[@]}
PRIMARY_FILE="${RENAMED[0]}"

if [[ "$DIAGRAM_COUNT" -gt 1 ]]; then
  echo "Generated ${DIAGRAM_COUNT} diagrams (all are uploaded):"
  for f in "${RENAMED[@]}"; do echo "  - $(basename "$f")"; done
  echo "Primary diagram (used for the PR comment/embed): $(basename "$PRIMARY_FILE")"
fi

# -----------------------------------------------------------------------------
# STEP 7: Output results to GitHub Actions variables
#
# These outputs can be used by subsequent steps in the workflow:
#   - result          : Exit code of jPipe Runner
#   - diagram_path    : Full path to the PRIMARY renamed diagram
#   - diagram_name    : File name of the primary diagram
#   - diagram_count   : How many diagrams were generated
#   - diagram_dir     : Folder holding every generated diagram
#   - runner_output   : Full console output from jPipe Runner
# -----------------------------------------------------------------------------
echo "result=$RESULT" >> "$GITHUB_OUTPUT"
echo "diagram_path=$PRIMARY_FILE" >> "$GITHUB_OUTPUT"
echo "diagram_name=$(basename "$PRIMARY_FILE")" >> "$GITHUB_OUTPUT"
echo "diagram_count=$DIAGRAM_COUNT" >> "$GITHUB_OUTPUT"
echo "diagram_dir=$DIAGRAM_DIR" >> "$GITHUB_OUTPUT"

echo "runner_output<<EOF" >> "$GITHUB_OUTPUT"
echo "$OUTPUT" >> "$GITHUB_OUTPUT"
echo "EOF" >> "$GITHUB_OUTPUT"

# -----------------------------------------------------------------------------
# STEP 8: Logging for debugging
# -----------------------------------------------------------------------------
echo "Diagram(s) saved to: $DIAGRAM_DIR"
ls -l -- "${RENAMED[@]}"
echo "diagram_count: $DIAGRAM_COUNT"
echo "diagram_path: $PRIMARY_FILE"
echo "diagram_name: $(basename "$PRIMARY_FILE")"
echo "Runner output:"
echo "$OUTPUT"
