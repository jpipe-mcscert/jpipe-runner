#!/usr/bin/env bash
set -euo pipefail

# Required env vars:
#   RESULT                # Exit code from jPipe Runner
#   EMBED_IMAGE           # true/false
#   ARTIFACT_URL
#   IMAGE_REPO
#   IMAGE_PATH
#   IMAGE_BRANCH
#   DIAGRAM_NAME
#   GITHUB_REPOSITORY
#   RUNNER_OUTPUT         # Multiline runner output

MSG_HEADER="Justification process"
if [[ "${RESULT}" == "0" ]]; then
  MSG_HEADER+=" completed!\n\n"
else
  MSG_HEADER+=" failed!\n\n"
fi

TARGET_REPO="${IMAGE_REPO:-$GITHUB_REPOSITORY}"

if [[ "${EMBED_IMAGE}" == "true" ]]; then
  # Clean up slashes from IMAGE_PATH
  CLEANED_PATH="${IMAGE_PATH#/}"
  CLEANED_PATH="${CLEANED_PATH%/}"
  REPO_NAME=$(basename "$GITHUB_REPOSITORY")
  RAW_URL="https://raw.githubusercontent.com/${TARGET_REPO}/${IMAGE_BRANCH}/${REPO_NAME}_${CLEANED_PATH}/${DIAGRAM_NAME}"
  MSG_BODY="![Generated Diagram](${RAW_URL})\n\n[Download Diagram Artifact](${ARTIFACT_URL})"
else
  MSG_BODY="[Download Diagram Artifact](${ARTIFACT_URL})"
fi

# Trim runner output for PR comment
TRIMMED=$(echo "$RUNNER_OUTPUT" | tail -n +10 | head -c 5000)
MSG_DETAILS="\n\n<details><summary>Runner Output</summary>\n\n\`\`\`\n$TRIMMED\n\`\`\`\n</details>"

# Output to GITHUB_OUTPUT for use in later steps
echo "msg<<EOF" >> "$GITHUB_OUTPUT"
echo -e "${MSG_HEADER}${MSG_BODY}${MSG_DETAILS}" >> "$GITHUB_OUTPUT"
echo "EOF" >> "$GITHUB_OUTPUT"
