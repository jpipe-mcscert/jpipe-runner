#!/usr/bin/env bash
set +e

# Required env vars:
#   PYTHON_PATH          # Path to Python interpreter
#   JD_FILE
#   VARIABLE
#   LIBRARY
#   CONFIG_FILE
#   DIAGRAM
#   DRY_RUN              # true/false
#   FORMAT               # Output format (default: svg)
#   COMMIT_SHA           # Commit SHA for naming output file


PYTHON_PATH="${PYTHON_PATH:-python}"
OUTPUT_DIR="/home/runner/work/"

echo "Using Python interpreter at: $PYTHON_PATH"

CMD="$PYTHON_PATH -m jpipe_runner '${JD_FILE}'"

append_flag() {
  local val="$1"; local flag="$2"
  [[ -n "$val" ]] && CMD+=" $flag '$val'"
}

handle_multiline_input() {
  local input="$1"; local flag="$2"
  while IFS= read -r line; do
    [[ -n "$line" ]] && CMD+=" $flag '$line'"
  done <<< "$input"
}

handle_multiline_input "${VARIABLE:-}" "--variable"
handle_multiline_input "${LIBRARY:-}" "--library"

append_flag "${CONFIG_FILE:-}" "--config-file"
append_flag "${DIAGRAM:-}" "--diagram"

[[ "${DRY_RUN:-false}" == "true" ]] && CMD+=" --dry-run"

CMD+=" --output-path $OUTPUT_DIR"
CMD+=" --format '${FORMAT:-svg}'"

echo "Running: $CMD"
OUTPUT=$(eval $CMD 2>&1)
RESULT=$?

echo "Command exited with code $RESULT"

ORIGINAL_FILE=$(find "$OUTPUT_DIR" -name "*.${FORMAT:-svg}" -type f | head -n1 || true)
if [[ -z "$ORIGINAL_FILE" ]]; then
  echo "No diagram file found in $OUTPUT_DIR"
  echo "result=1" >> "$GITHUB_OUTPUT"
  exit 0
fi
BASENAME=$(basename "$ORIGINAL_FILE" .${FORMAT:-svg})
RENAMED_FILE="${OUTPUT_DIR}${BASENAME}_${COMMIT_SHA}.${FORMAT:-svg}"

mv "$ORIGINAL_FILE" "$RENAMED_FILE"

echo "result=$RESULT" >> "$GITHUB_OUTPUT"
echo "diagram_path=$RENAMED_FILE" >> "$GITHUB_OUTPUT"
echo "diagram_name=$(basename "$RENAMED_FILE")" >> "$GITHUB_OUTPUT"
echo "runner_output<<EOF" >> "$GITHUB_OUTPUT"
echo "$OUTPUT" >> "$GITHUB_OUTPUT"
echo "EOF" >> "$GITHUB_OUTPUT"

echo "Diagram saved to: $RENAMED_FILE"
ls -l "$RENAMED_FILE"
# print diagram_path and diagram_name
echo "diagram_path: $RENAMED_FILE"
echo "diagram_name: $(basename "$RENAMED_FILE")"
echo "Runner output:"
echo "$OUTPUT"
