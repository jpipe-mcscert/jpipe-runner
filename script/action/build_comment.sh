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
#   GITHUB_TOKEN    : GitHub token for API access
#   GITHUB_READONLY_TOKEN: Read-only token for generating signed URLs
###############################################################################

echo "Starting PR comment build..."

# -----------------------------------------------------------------------------
# STEP 1: Build the header
# -----------------------------------------------------------------------------
MSG_HEADER="Justification process"
if [[ "${RESULT}" == "0" ]]; then
  MSG_HEADER+=" completed!\n\n"
else
  MSG_HEADER+=" failed!\n\n"
fi
echo "Building header. RESULT=${RESULT}"

# -----------------------------------------------------------------------------
# STEP 2: Build the image section (with signed token URL for private repos)
# -----------------------------------------------------------------------------
TARGET_REPO="${IMAGE_REPO:-$GITHUB_REPOSITORY}"
echo "Target repo: ${TARGET_REPO}"

if [[ "${EMBED_IMAGE}" == "true" ]]; then
  CLEANED_PATH="${IMAGE_PATH#/}"   # Remove leading slash
  CLEANED_PATH="${CLEANED_PATH%/}" # Remove trailing slash
  REPO_NAME=$(basename "$GITHUB_REPOSITORY")
  IMAGE_FILE_PATH="${REPO_NAME}_${CLEANED_PATH}/${DIAGRAM_NAME}"
  echo "Image file path: ${IMAGE_FILE_PATH}"

  # Choose the token: prefer read-only, fallback to default
  if [[ -n "${GITHUB_READONLY_TOKEN:-}" ]]; then
    echo "Using GITHUB_READONLY_TOKEN."
    API_TOKEN="${GITHUB_READONLY_TOKEN}"
  elif [[ -n "${GITHUB_TOKEN:-}" ]]; then
    echo "Using GITHUB_TOKEN as fallback."
    API_TOKEN="${GITHUB_TOKEN}"
  else
    echo "Error: GITHUB_READONLY_TOKEN or GITHUB_TOKEN must be set."
    exit 1
  fi


  # Detect if repo is private
  IS_PRIVATE=$(curl -s -H "Authorization: token $API_TOKEN" "https://api.github.com/repos/${TARGET_REPO}" | jq -r .private)
  echo "Repo private: ${IS_PRIVATE}"

  if [[ "$IS_PRIVATE" == "true" ]]; then
    echo "Fetching signed download URL for private repo..."
    # Get signed temporary download URL using selected token
    RAW_URL=$(curl -s -H "Authorization: token $API_TOKEN" \
      "https://api.github.com/repos/${TARGET_REPO}/contents/${IMAGE_FILE_PATH}?ref=${IMAGE_BRANCH}" \
      | jq -r .download_url)
    echo "RAW_URL (private): ${RAW_URL}"
  else
    # Public repo: direct raw.githubusercontent.com URL
    RAW_URL="https://raw.githubusercontent.com/${TARGET_REPO}/${IMAGE_BRANCH}/${IMAGE_FILE_PATH}"
    echo "RAW_URL (public): ${RAW_URL}"
  fi

  if [[ "${RESULT}" == "0" ]]; then
    MSG_BODY="<details><summary>View Generated Diagram</summary>\n\n![Generated Diagram](${RAW_URL})\n\n[Download Diagram Artifact](${ARTIFACT_URL})\n</details>"
    echo "Success: Diagram embedded in collapsible section."
  else
    MSG_BODY="![Generated Diagram](${RAW_URL})\n\n[Download Diagram Artifact](${ARTIFACT_URL})"
    echo "Failure: Diagram shown without collapse."
  fi
else
  MSG_BODY="[Download Diagram Artifact](${ARTIFACT_URL})"
  echo "No image embedding requested. Using download link only."
fi


# -----------------------------------------------------------------------------
# STEP 3: Clean and format runner output for failure case
# -----------------------------------------------------------------------------
if [[ "${RESULT}" == "0" ]]; then
  # On SUCCESS: no runner output shown
  MSG_DETAILS=""
  echo "Success: No runner output to show."
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
  echo "Cleaning runner output: removed first 9 lines."

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
  echo "Cleaning runner output: removed jPipeRunner ASCII logo and trailing text."

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
  echo "Cleaning runner output: removed ANSI color codes."

  ###########################################################################
  # Wrap the cleaned output in a collapsible <details> block for the PR
  ###########################################################################
  MSG_DETAILS="\n\n<details><summary>Runner Output</summary>\n\n\`\`\`\n$CLEANED_OUTPUT\n\`\`\`\n</details>"
  echo "Runner output cleaned and wrapped in collapsible section."
fi

# -----------------------------------------------------------------------------
# STEP 4: Send final message to GitHub Actions output
# -----------------------------------------------------------------------------
{
  echo "msg<<EOF"
  echo -e "${MSG_HEADER}${MSG_BODY}${MSG_DETAILS}"
  echo "EOF"
} >> "$GITHUB_OUTPUT"
