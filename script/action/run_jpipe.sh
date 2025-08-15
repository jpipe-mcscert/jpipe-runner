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
#   PYTHON_PATH   : Path to Python interpreter (default: "python" if unset)
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
PYTHON_PATH="${PYTHON_PATH:-python}"
OUTPUT_DIR="/home/runner/work/"

echo "Using Python interpreter at: $PYTHON_PATH"

# Base command to run
CMD="$PYTHON_PATH -m jpipe_runner '${JD_FILE}'"

# -----------------------------------------------------------------------------
# STEP 2: Helper functions for appending flags
# -----------------------------------------------------------------------------
append_flag() {
  # Appends a flag with its value if the value is non-empty
  local val="$1"
  local flag="$2"
  [[ -n "$val" ]] && CMD+=" $flag '$val'"
}

handle_multiline_input() {
  # Appends a flag for each non-empty line in multi-line input
  local input="$1"
  local flag="$2"
  while IFS= read -r line; do
    [[ -n "$line" ]] && CMD+=" $flag '$line'"
  done <<< "$input"
}

# -----------------------------------------------------------------------------
# STEP 3: Append command arguments from environment variables
# -----------------------------------------------------------------------------
handle_multiline_input "${VARIABLE:-}" "--variable"
handle_multiline_input "${LIBRARY:-}" "--library"

append_flag "${CONFIG_FILE:-}" "--config-file"
append_flag "${DIAGRAM:-}" "--diagram"

[[ "${DRY_RUN:-false}" == "true" ]] && CMD+=" --dry-run"

CMD+=" --output-path $OUTPUT_DIR"
CMD+=" --format '${FORMAT:-svg}'"

# -----------------------------------------------------------------------------
# STEP 4: Run the command and capture output
# -----------------------------------------------------------------------------
echo "Running: $CMD"
OUTPUT=$(eval $CMD 2>&1)  # Capture both stdout and stderr
RESULT=$?

echo "Command exited with code $RESULT"

# -----------------------------------------------------------------------------
# STEP 5: Locate generated diagram
#
# Why:
#   jPipe Runner saves the diagram into OUTPUT_DIR with a name that may vary.
#
# How:
#   - Find the first file matching "*.<format>" in the directory.
#   - If none found, set result=1 and exit gracefully.
# -----------------------------------------------------------------------------
ORIGINAL_FILE=$(find "$OUTPUT_DIR" -name "*.${FORMAT:-svg}" -type f | head -n1 || true)
if [[ -z "$ORIGINAL_FILE" ]]; then
  echo "No diagram file found in $OUTPUT_DIR"
  echo "result=1" >> "$GITHUB_OUTPUT"
  exit 0
fi

# -----------------------------------------------------------------------------
# STEP 6: Rename diagram file to include commit SHA
#
# Why:
#   - This prevents overwriting in artifact storage.
#   - Allows traceability back to the commit that generated the diagram.
#
# Example:
#   mydiagram.svg -> mydiagram_<COMMIT_SHA>.svg
# -----------------------------------------------------------------------------
BASENAME=$(basename "$ORIGINAL_FILE" .${FORMAT:-svg})
RENAMED_FILE="${OUTPUT_DIR}${BASENAME}_${COMMIT_SHA}.${FORMAT:-svg}"

mv "$ORIGINAL_FILE" "$RENAMED_FILE"

# -----------------------------------------------------------------------------
# STEP 7: Output results to GitHub Actions variables
#
# These outputs can be used by subsequent steps in the workflow:
#   - result          : Exit code of jPipe Runner
#   - diagram_path    : Full path to renamed diagram
#   - diagram_name    : File name of renamed diagram
#   - runner_output   : Full console output from jPipe Runner
# -----------------------------------------------------------------------------
echo "result=$RESULT" >> "$GITHUB_OUTPUT"
echo "diagram_path=$RENAMED_FILE" >> "$GITHUB_OUTPUT"
echo "diagram_name=$(basename "$RENAMED_FILE")" >> "$GITHUB_OUTPUT"

echo "runner_output<<EOF" >> "$GITHUB_OUTPUT"
echo "$OUTPUT" >> "$GITHUB_OUTPUT"
echo "EOF" >> "$GITHUB_OUTPUT"

# -----------------------------------------------------------------------------
# STEP 8: Logging for debugging
# -----------------------------------------------------------------------------
echo "Diagram saved to: $RENAMED_FILE"
ls -l "$RENAMED_FILE"
echo "diagram_path: $RENAMED_FILE"
echo "diagram_name: $(basename "$RENAMED_FILE")"
echo "Runner output:"
echo "$OUTPUT"
