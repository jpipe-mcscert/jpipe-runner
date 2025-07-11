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

# Upload each .changes file to PPA
for changes in "${CHANGES_FILES[@]}"; do
  echo "Uploading $changes to PPA $PPA..."
  dput ppa:"$PPA" "$changes"
  if [ $? -ne 0 ]; then
    echo "Error uploading $changes to PPA"
    exit 1
  fi
done

echo "All uploads completed successfully."
