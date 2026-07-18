#!/bin/bash

PPA="$1"           # e.g. mcscert/ppa
shift
CHANGES_FILES=("$@")  # one or more .changes files

if [ -z "$PPA" ] || [ ${#CHANGES_FILES[@]} -eq 0 ]; then
  echo "Usage: $0 <ppa-owner/ppa-name> <path-to-.changes> [<path-to-another-.changes> ...]"
  exit 1
fi

# Install upload tools (if not already installed)
sudo apt update
sudo apt install -y dput devscripts

# Number of upload attempts per .changes file, to ride out transient Launchpad
# upload errors (e.g. FTP "550 Requested action not taken: internal server
# error"). Overridable via the environment.
MAX_RETRIES="${MAX_RETRIES:-3}"
RETRY_DELAY="${RETRY_DELAY:-10}"

# Upload each .changes file to the PPA. A single failing distro must not abort
# the whole batch (that would leave the remaining distros — and the downstream
# Homebrew publish — unprocessed), so we retry transient errors, treat an
# already-uploaded distro as done, keep going, and fail at the end only if a
# distro genuinely could not be uploaded.
failures=()
for changes in "${CHANGES_FILES[@]}"; do
  echo "Uploading $changes to PPA $PPA..."
  uploaded=false
  for attempt in $(seq 1 "$MAX_RETRIES"); do
    if out=$(dput ppa:"$PPA" "$changes" 2>&1); then
      echo "$out"
      uploaded=true
      break
    fi
    echo "$out"
    # Launchpad already has this version for this series — nothing more to do.
    if grep -qiE "already (uploaded|registered|exists)" <<<"$out"; then
      echo "Note: $changes appears to be already uploaded; treating as done."
      uploaded=true
      break
    fi
    echo "Upload attempt $attempt/$MAX_RETRIES for $changes failed; retrying in ${RETRY_DELAY}s..."
    sleep "$RETRY_DELAY"
  done

  if ! $uploaded; then
    echo "Error: could not upload $changes after $MAX_RETRIES attempts"
    failures+=("$changes")
  fi
done

if [ ${#failures[@]} -gt 0 ]; then
  echo "The following uploads failed: ${failures[*]}"
  exit 1
fi

echo "All uploads completed successfully."
