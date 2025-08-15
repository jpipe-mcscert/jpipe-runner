#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# PR COMMENT MESSAGE BUILDER
#
# This script formats the output from the jpipe-runner execution into a PR comment.
# It:
#   1. Adds a header showing success or failure.
#   2. Includes an image (collapsed on success, visible on failure).
#   3. Cleans the runner output:
#       - On SUCCESS: hides the runner output entirely.
#       - On FAILURE:
#           a) Removes the first 9 lines (ASCII warning banner).
#           b) Removes everything from the jPipeRunner ASCII logo to the end.
#           c) Removes ANSI color codes.
#
# IMPORTANT:
#   If the runner's ASCII banner or jPipeRunner output format changes, you MUST
#   update:
#       - The "tail -n +10" line count (to match the new banner length).
#       - The sed pattern used to detect the start of the jPipeRunner ASCII.
#
# ENVIRONMENT VARIABLES REQUIRED:
#   RESULT          : "0" for success, "1" for failure
#   EMBED_IMAGE     : "true" to include diagram image
#   ARTIFACT_URL    : URL to download diagram
#   IMAGE_REPO      : Repository for image hosting (defaults to GITHUB_REPOSITORY)
#   IMAGE_PATH      : Path to image in repo
#   IMAGE_BRANCH    : Branch name for hosted image
#   DIAGRAM_NAME    : Diagram filename
#   GITHUB_REPOSITORY: Repo name in GitHub
#   RUNNER_OUTPUT   : Full text output from runner execution
###############################################################################

# -----------------------------------------------------------------------------
# STEP 1: Build the header
# -----------------------------------------------------------------------------
MSG_HEADER="Justification process"
if [[ "${RESULT}" == "0" ]]; then
  MSG_HEADER+=" completed!\n\n"
else
  MSG_HEADER+=" failed!\n\n"
fi

# -----------------------------------------------------------------------------
# STEP 2: Build the image section (with signed token URL for private repos)
# -----------------------------------------------------------------------------
TARGET_REPO="${IMAGE_REPO:-$GITHUB_REPOSITORY}"

if [[ "${EMBED_IMAGE}" == "true" ]]; then
  CLEANED_PATH="${IMAGE_PATH#/}"   # Remove leading slash
  CLEANED_PATH="${CLEANED_PATH%/}" # Remove trailing slash
  REPO_NAME=$(basename "$GITHUB_REPOSITORY")
  IMAGE_FILE_PATH="${REPO_NAME}_${CLEANED_PATH}/${DIAGRAM_NAME}"

  # Detect if repo is private
  IS_PRIVATE=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
    "https://api.github.com/repos/${TARGET_REPO}" | jq -r .private)

  if [[ "$IS_PRIVATE" == "true" ]]; then
    # Get signed temporary download URL
    RAW_URL=$(curl -s -H "Authorization: token $GITHUB_TOKEN" \
      "https://api.github.com/repos/${TARGET_REPO}/contents/${IMAGE_FILE_PATH}?ref=${IMAGE_BRANCH}" \
      | jq -r .download_url)
  else
    # Public repo: direct raw.githubusercontent.com URL
    RAW_URL="https://raw.githubusercontent.com/${TARGET_REPO}/${IMAGE_BRANCH}/${IMAGE_FILE_PATH}"
  fi

  if [[ "${RESULT}" == "0" ]]; then
    MSG_BODY="<details><summary>View Generated Diagram</summary>\n\n![Generated Diagram](${RAW_URL})\n\n[Download Diagram Artifact](${ARTIFACT_URL})\n</details>"
  else
    MSG_BODY="![Generated Diagram](${RAW_URL})\n\n[Download Diagram Artifact](${ARTIFACT_URL})"
  fi
else
  MSG_BODY="[Download Diagram Artifact](${ARTIFACT_URL})"
fi


# -----------------------------------------------------------------------------
# STEP 3: Clean and format runner output for failure case
# -----------------------------------------------------------------------------
if [[ "${RESULT}" == "0" ]]; then
  # On SUCCESS: no runner output shown
  MSG_DETAILS=""
else
  ###########################################################################
  # CLEAN STEP 1: Remove the first 9 lines
  #
  # Why:
  #   The runner always prints an initial ASCII warning banner + header
  #   before the actual failure log text starts.
  #
  # Example (to be removed):
  #   _____ ____ ____ ___ ____ _ ___ ____
  #   | ____| _ \| _ \ / _ \| _ \ | | / _ \ / ___|
  #   ... (total of 9 lines)
  #
  # If the banner changes length, update the number in "tail -n +10".
  ###########################################################################
  CLEANED_OUTPUT=$(echo "$RUNNER_OUTPUT" | tail -n +10)

  ###########################################################################
  # CLEAN STEP 2: Remove from jPipeRunner ASCII logo to end of output
  #
  # Why:
  #   After the error message, the runner prints a jPipeRunner ASCII logo and
  #   a table of checks (PASS/FAIL/SKIP) plus a diagram path. These are noise
  #   for the PR comment.
  #
  # Example start of section to remove:
  #       _ ____  _               ____
  #      (_)  _ \(_)_ __   ___   |  _ \ _   _ _ __ ...
  #
  # Regex to detect the logo's first line is: /^    _ ____  _/
  #
  # If the logo changes (spacing, underscores, etc.), update this pattern.
  ###########################################################################
  CLEANED_OUTPUT=$(echo "$CLEANED_OUTPUT" | sed '/^    _ ____  _/,$d')

  ###########################################################################
  # CLEAN STEP 3: Strip ANSI color codes
  #
  # Why:
  #   The runner output may contain color codes like:
  #     ^[[91mFAIL^[[0m
  #
  #   These should be removed so the PR comment shows clean text.
  #
  # Regex matches ESC[...m or ESC[...K sequences.
  ###########################################################################
  CLEANED_OUTPUT=$(echo "$CLEANED_OUTPUT" | sed 's/\x1B\[[0-9;]*[mK]//g')

  ###########################################################################
  # Wrap the cleaned output in a collapsible <details> block for the PR
  ###########################################################################
  MSG_DETAILS="\n\n<details><summary>Runner Output</summary>\n\n\`\`\`\n$CLEANED_OUTPUT\n\`\`\`\n</details>"
fi

# -----------------------------------------------------------------------------
# STEP 4: Send final message to GitHub Actions output
# -----------------------------------------------------------------------------
{
  echo "msg<<EOF"
  echo -e "${MSG_HEADER}${MSG_BODY}${MSG_DETAILS}"
  echo "EOF"
} >> "$GITHUB_OUTPUT"
