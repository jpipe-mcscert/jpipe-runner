#!/usr/bin/env bash
set -euo pipefail

# Required env vars:
#   GITHUB_TOKEN
#   IMAGE_FILE
#   IMAGE_NAME
#   IMAGE_REPO
#   IMAGE_BRANCH
#   IMAGE_PATH
#   IMAGE_COMMIT_MESSAGE
#   GITHUB_REPOSITORY

TARGET_REPO="${IMAGE_REPO:-$GITHUB_REPOSITORY}"

# Clone the target repo
git clone "https://x-access-token:${GITHUB_TOKEN}@github.com/${TARGET_REPO}.git" repo
cd repo

# Ensure branch exists
git fetch origin "${IMAGE_BRANCH}"
if ! git show-ref --quiet "refs/remotes/origin/${IMAGE_BRANCH}"; then
  echo "Branch '${IMAGE_BRANCH}' does not exist."
  exit 1
fi

git checkout "${IMAGE_BRANCH}"

# Store under folder like <repo_name>_<image_path>
REPO_NAME=$(basename "$GITHUB_REPOSITORY")
TARGET_FOLDER="${REPO_NAME}_${IMAGE_PATH}"
mkdir -p "$TARGET_FOLDER"
cp "$IMAGE_FILE" "$TARGET_FOLDER/$IMAGE_NAME"

# Commit & push
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add -A
git commit -m "${IMAGE_COMMIT_MESSAGE}" || echo "No changes to commit"
git push origin "${IMAGE_BRANCH}"
