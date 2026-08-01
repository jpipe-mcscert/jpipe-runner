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
#       - On FAILURE: removes ANSI color codes so the PR comment stays readable.
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
#   GITHUB_READONLY_TOKEN: Read-only token for generating signed URLs for accessing URLs in private repositories
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
#
# WHY THE DIAGRAM IS COMMITTED TO A BRANCH:
#   GitHub renders markdown images through its "camo" proxy, which fetches the
#   URL ANONYMOUSLY. Committing the diagram to a branch yields a
#   raw.githubusercontent.com URL that camo can reach. Artifact URLs require the
#   viewer to be logged in, so they can never be embedded — the artifact link is
#   only ever a download link.
#
# PRIVATE REPOS ARE BEST-EFFORT:
#   No anonymously-reachable URL can exist for a private repo, so we fall back to
#   the contents API `download_url`, which carries a TIME-LIMITED token. It works
#   because camo fetches and caches the image the first time the comment renders,
#   but if camo ever re-fetches after that token expires the image will break.
#   The artifact download link is always included as a durable fallback.
# -----------------------------------------------------------------------------
TARGET_REPO="${IMAGE_REPO:-$GITHUB_REPOSITORY}"
echo "Target repo: ${TARGET_REPO}"

# The artifact upload step is skipped when the runner produced no diagram, in which
# case ARTIFACT_URL is empty. Build the download link conditionally so we never emit
# an empty markdown link like "[Download Diagram Artifact]()".
if [[ -n "${ARTIFACT_URL:-}" ]]; then
  DOWNLOAD_LINK="[Download Diagram Artifact](${ARTIFACT_URL})"
else
  DOWNLOAD_LINK="_No diagram artifact was produced for this run._"
  echo "::warning::No diagram artifact URL available; omitting the download link."
fi

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


  API="https://api.github.com"
  AUTH_HEADER="Authorization: token ${API_TOKEN}"
  RAW_URL=""

  # Detect if repo is private.
  #
  # On ANY failure we deliberately assume "private". The public raw URL is
  # guaranteed to 404 for a private repo, so guessing "public" would embed a
  # broken image; assuming private merely routes us through the signed-URL path,
  # which fails safe to a link-only comment below if it cannot be resolved.
  IS_PRIVATE="true"
  if REPO_JSON=$(curl -fsS -H "$AUTH_HEADER" "${API}/repos/${TARGET_REPO}"); then
    PRIVATE_FIELD=$(jq -r '.private // empty' <<<"$REPO_JSON")
    if [[ "$PRIVATE_FIELD" == "false" ]]; then
      IS_PRIVATE="false"
    elif [[ "$PRIVATE_FIELD" != "true" ]]; then
      echo "::warning::Could not read repository visibility for ${TARGET_REPO}; assuming private."
    fi
  else
    echo "::warning::Visibility lookup failed for ${TARGET_REPO}; assuming private."
  fi
  echo "Repo private: ${IS_PRIVATE}"

  if [[ "$IS_PRIVATE" == "false" ]]; then
    # Public repo: direct raw.githubusercontent.com URL (stable, anonymous).
    RAW_URL="https://raw.githubusercontent.com/${TARGET_REPO}/${IMAGE_BRANCH}/${IMAGE_FILE_PATH}"
    echo "RAW_URL (public): ${RAW_URL}"
  else
    # Private repo: ask the contents API for a signed download_url. Retry briefly
    # to absorb the propagation delay between commit_diagram.sh pushing the image
    # and the API serving it on that branch.
    echo "Fetching signed download URL for private repo..."
    for attempt in 1 2 3; do
      if CONTENTS_JSON=$(curl -fsS -H "$AUTH_HEADER" \
          "${API}/repos/${TARGET_REPO}/contents/${IMAGE_FILE_PATH}?ref=${IMAGE_BRANCH}"); then
        CANDIDATE=$(jq -r '.download_url // empty' <<<"$CONTENTS_JSON")
        if [[ -n "$CANDIDATE" ]]; then
          RAW_URL="$CANDIDATE"
          break
        fi
      fi
      if (( attempt < 3 )); then
        echo "Signed URL not available yet (attempt ${attempt}/3); retrying in 3s..."
        sleep 3
      fi
    done

    if [[ -n "$RAW_URL" ]]; then
      echo "RAW_URL (private): signed URL resolved"
    else
      echo "::warning::Could not resolve a signed download URL for ${IMAGE_FILE_PATH} on branch ${IMAGE_BRANCH}. Posting the artifact link without an inline preview."
    fi
  fi

  # Fail safe: never interpolate an empty URL into the comment — that would render
  # as a broken image. Degrade to the artifact download link instead.
  if [[ -z "$RAW_URL" ]]; then
    MSG_BODY="${DOWNLOAD_LINK}"
    echo "Embedding unavailable: using download link only."
  elif [[ "${RESULT}" == "0" ]]; then
    MSG_BODY="<details><summary>View Generated Diagram</summary>\n\n![Generated Diagram](${RAW_URL})\n\n${DOWNLOAD_LINK}\n</details>"
    echo "Success: Diagram embedded in collapsible section."
  else
    MSG_BODY="![Generated Diagram](${RAW_URL})\n\n${DOWNLOAD_LINK}"
    echo "Failure: Diagram shown without collapse."
  fi
else
  MSG_BODY="${DOWNLOAD_LINK}"
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
  CLEANED_OUTPUT=$(echo "$RUNNER_OUTPUT" | sed 's/\x1B\[[0-9;]*[mK]//g')
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
