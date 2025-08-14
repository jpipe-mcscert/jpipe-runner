#!/usr/bin/env bash
set -euo pipefail

# -----------------------------------------------------------------------------
# build_comment.sh
#
# This script builds the PR comment message for the jPipe Runner GitHub Action.
# It handles different output formatting depending on the result of the runner.
#
# Required environment variables:
#   RESULT         - Exit code from jPipe Runner (0 = success, 1 = error, others = fallback)
#   EMBED_IMAGE    - "true" or "false", whether to embed the diagram image
#   ARTIFACT_URL   - URL to download the generated diagram artifact
#   IMAGE_REPO     - (optional) Target repo for image commit
#   IMAGE_PATH     - Path where image is stored
#   IMAGE_BRANCH   - Branch where image is committed
#   DIAGRAM_NAME   - Name of the generated diagram file
#   GITHUB_REPOSITORY - Current GitHub repository
#   RUNNER_OUTPUT  - Multiline output from the runner (stdout + stderr)
#
# Output:
#   Writes the formatted comment message to $GITHUB_OUTPUT for use in later steps.
# -----------------------------------------------------------------------------

# Build the message header based on the result
MSG_HEADER="Justification process"
if [[ "${RESULT}" == "0" ]]; then
  MSG_HEADER+=" completed!\n\n"
else
  MSG_HEADER+=" failed!\n\n"
fi

# Determine the target repo for image embedding
TARGET_REPO="${IMAGE_REPO:-$GITHUB_REPOSITORY}"

# Build the image markdown if embedding is enabled
if [[ "${EMBED_IMAGE}" == "true" ]]; then
  # Remove leading/trailing slashes from IMAGE_PATH for URL construction
  CLEANED_PATH="${IMAGE_PATH#/}"
  CLEANED_PATH="${CLEANED_PATH%/}"
  REPO_NAME=$(basename "$GITHUB_REPOSITORY")
  RAW_URL="https://raw.githubusercontent.com/${TARGET_REPO}/${IMAGE_BRANCH}/${REPO_NAME}_${CLEANED_PATH}/${DIAGRAM_NAME}"
  IMAGE_MD="![Generated Diagram](${RAW_URL})"
else
  IMAGE_MD=""
fi

# Always provide the artifact download link
ARTIFACT_MD="[Download Diagram Artifact](${ARTIFACT_URL})"

# -----------------------------------------------------------------------------
# Output formatting logic:
#
# 1. On success (RESULT == 0):
#    - Collapse the image and artifact link in a <details> block.
#    - Do NOT show any runner output.
#
# 2. On error (RESULT == 1):
#    - Show only the relevant error messages from the runner output.
#    - Remove the first 9 lines (these are usually banner lines).
#    - Remove all lines from the ASCII art (the line starting with '_ ____') to the end.
#      NOTE: If the ASCII art or runner output format changes, update the pattern below.
#
# 3. On other results:
#    - Show artifact and trimmed runner output (remove first 9 lines, limit to 5000 chars).
# -----------------------------------------------------------------------------

if [[ "${RESULT}" == "0" ]]; then
  # Success: collapse image and artifact, no runner output
  MSG_BODY="\n<details><summary>Generated Diagram</summary>\n\n${IMAGE_MD}\n\n${ARTIFACT_MD}\n</details>"
elif [[ "${RESULT}" == "1" ]]; then
  # Error: show only error messages, remove first 9 lines and ASCII art to end

  # --- IMPORTANT FOR MAINTAINERS ---
  # The following trims the runner output:
  #   1. Removes the first 9 lines (setup, banners, etc.)
  #   2. Removes everything from the line starting with '_ ____' (ASCII art) to the end.
  # If the runner output or ASCII art changes, update the pattern in the awk command below.
  # ---------------------------------
  TRIMMED=$(echo "$RUNNER_OUTPUT" | tail -n +10 | awk '/^_ ____/{exit} {print}' | head -c 5000)

  MSG_BODY="\n${ARTIFACT_MD}\n\n<details><summary>Runner Output</summary>\n\n\`\`\`\n${TRIMMED}\n\`\`\`\n</details>"
else
  # Fallback: show artifact and trimmed runner output (remove first 9 lines, limit to 5000 chars)
  TRIMMED=$(echo "$RUNNER_OUTPUT" | tail -n +10 | head -c 5000)
  MSG_BODY="\n${ARTIFACT_MD}\n\n<details><summary>Runner Output</summary>\n\n\`\`\`\n${TRIMMED}\n\`\`\`\n</details>"
fi

# Output the message for use in the next GitHub Action step
echo "msg<<EOF" >> "$GITHUB_OUTPUT"
echo -e "${MSG_HEADER}${MSG_BODY}" >> "$GITHUB_OUTPUT"
echo "EOF" >> "$GITHUB_OUTPUT"

# -----------------------------------------------------------------------------
# MAINTAINER NOTES:
#
# - The logic for trimming the runner output is sensitive to the output format.
# - If the ASCII art or the number of setup lines changes, update:
#     - The 'tail -n +10' (removes first 9 lines)
#     - The awk pattern '/^_ ____/{exit}' (stops at ASCII art)
# - Always test changes to this script to ensure PR comments are formatted correctly.
# -----------------------------------------------------------------------------
