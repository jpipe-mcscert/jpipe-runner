#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# IMAGE UPLOADER TO GITHUB REPO
#
# This script uploads an image (e.g., a generated diagram) to a GitHub
# repository, under a specified branch and path. It:
#   1. Clones the target repository.
#   2. Ensures the target branch exists.
#   3. Places the image into a subfolder named:
#         <source_repo_name>_<image_path>
#   4. Commits and pushes the changes.
#
# Required Environment Variables:
#   GITHUB_TOKEN        : Token with push permissions to the target repository.
#   IMAGE_FILE          : Local path to the image file to upload.
#   IMAGE_NAME          : Name to assign to the image in the repository.
#   IMAGE_REPO          : (Optional) Target repository in format "owner/repo".
#                         Defaults to GITHUB_REPOSITORY.
#   IMAGE_BRANCH        : Branch to push the image to (must already exist).
#   IMAGE_PATH          : Path inside the repository (without leading/trailing slash).
#   IMAGE_COMMIT_MESSAGE: Commit message for the uploaded image.
#   GITHUB_REPOSITORY   : Full name of the repository running this script.
###############################################################################

# -----------------------------------------------------------------------------
# STEP 1: Determine target repository
# If IMAGE_REPO is unset, default to current repo (GITHUB_REPOSITORY)
# -----------------------------------------------------------------------------
TARGET_REPO="${IMAGE_REPO:-$GITHUB_REPOSITORY}"

# -----------------------------------------------------------------------------
# STEP 2: Clone the target repository using GitHub token for authentication
# -----------------------------------------------------------------------------
git clone "https://x-access-token:${GITHUB_TOKEN}@github.com/${TARGET_REPO}.git" repo
cd repo

# -----------------------------------------------------------------------------
# STEP 3: Ensure the target branch exists
#
# Why:
#   This script will fail if it tries to push to a branch that does not exist.
#
# How:
#   - Fetch the branch from origin
#   - Check its existence with "git show-ref"
#
# Maintenance:
#   If you want the script to create the branch automatically instead of failing,
#   replace the "exit 1" block with a "git checkout -b" command.
# -----------------------------------------------------------------------------
git fetch origin "${IMAGE_BRANCH}"
if ! git show-ref --quiet "refs/remotes/origin/${IMAGE_BRANCH}"; then
  echo "Branch '${IMAGE_BRANCH}' does not exist."
  exit 1
fi

# Switch to target branch
git checkout "${IMAGE_BRANCH}"

# -----------------------------------------------------------------------------
# STEP 4: Prepare the target folder in the repository
#
# Folder structure:
#   <source_repo_name>_<IMAGE_PATH>
#
# Example:
#   If GITHUB_REPOSITORY="my-org/my-project"
#   and IMAGE_PATH="notebooks/quality"
#   then TARGET_FOLDER="my-project_notebooks/quality"
#
# Maintenance:
#   Changing this folder naming pattern will affect all scripts that retrieve
#   these images. Ensure consistency across workflows.
# -----------------------------------------------------------------------------
REPO_NAME=$(basename "$GITHUB_REPOSITORY")
TARGET_FOLDER="${REPO_NAME}_${IMAGE_PATH}"
mkdir -p "$TARGET_FOLDER"

# Copy image into the target folder
cp "$IMAGE_FILE" "$TARGET_FOLDER/$IMAGE_NAME"

# -----------------------------------------------------------------------------
# STEP 5: Commit and push the image
#
# - Sets Git user info for GitHub Actions bot.
# - Adds and commits changes.
# - If there are no changes (e.g., file is identical), skip commit gracefully.
# -----------------------------------------------------------------------------
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"

git add -A
git commit -m "${IMAGE_COMMIT_MESSAGE}" || echo "No changes to commit"

git push origin "${IMAGE_BRANCH}"
