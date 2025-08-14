#!/usr/bin/env bash
set -euo pipefail

# Required env vars:
#   RESULT
#   EMBED_IMAGE
#   ARTIFACT_URL
#   IMAGE_REPO
#   IMAGE_PATH
#   IMAGE_BRANCH
#   DIAGRAM_NAME
#   GITHUB_REPOSITORY
#   RUNNER_OUTPUT

MSG_HEADER="Justification process"
if [[ "${RESULT}" == "0" ]]; then
  MSG_HEADER+=" completed!\n\n"
else
  MSG_HEADER+=" failed!\n\n"
fi

TARGET_REPO="${IMAGE_REPO:-$GITHUB_REPOSITORY}"

if [[ "${EMBED_IMAGE}" == "true" ]]; then
  CLEANED_PATH="${IMAGE_PATH#/}"
  CLEANED_PATH="${CLEANED_PATH%/}"
  REPO_NAME=$(basename "$GITHUB_REPOSITORY")
  RAW_URL="https://raw.githubusercontent.com/${TARGET_REPO}/${IMAGE_BRANCH}/${REPO_NAME}_${CLEANED_PATH}/${DIAGRAM_NAME}"
  if [[ "${RESULT}" == "0" ]]; then
    # Collapse image on success
    MSG_BODY="<details><summary>View Generated Diagram</summary>\n\n![Generated Diagram](${RAW_URL})\n\n[Download Diagram Artifact](${ARTIFACT_URL})\n</details>"
  else
    # Show image normally on failure
    MSG_BODY="![Generated Diagram](${RAW_URL})\n\n[Download Diagram Artifact](${ARTIFACT_URL})"
  fi
else
  MSG_BODY="[Download Diagram Artifact](${ARTIFACT_URL})"
fi

# Trim runner output for PR comment
if [[ "${RESULT}" == "0" ]]; then
  # No runner output on success
  MSG_DETAILS=""
else
  # Remove first 9 lines
  CLEANED_OUTPUT=$(echo "$RUNNER_OUTPUT" | tail -n +10)
  # Remove everything from the "jPipe Files" section to the end
  CLEANED_OUTPUT=$(echo "$CLEANED_OUTPUT" | sed '/^  jPipe Files/,$d')
  MSG_DETAILS="\n\n<details><summary>Runner Output</summary>\n\n\`\`\`\n$CLEANED_OUTPUT\n\`\`\`\n</details>"
fi

# Output to GITHUB_OUTPUT
{
  echo "msg<<EOF"
  echo -e "${MSG_HEADER}${MSG_BODY}${MSG_DETAILS}"
  echo "EOF"
} >> "$GITHUB_OUTPUT"
