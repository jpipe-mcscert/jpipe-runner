#!/bin/bash

PPA="$1"           # e.g. mcscert/ppa
CHANGES_FILE="$2"  # e.g. deb_dist/*.changes

if [ -z "$PPA" ] || [ -z "$CHANGES_FILE" ]; then
  echo "Usage: $0 <ppa-owner/ppa-name> <path-to-.changes>"
  exit 1
fi

# Install upload tools (if not already available)
sudo apt update
sudo apt install -y dput devscripts

# Upload to PPA
dput ppa:"$PPA" "$CHANGES_FILE"

if [ $? -ne 0 ]; then
  echo "Error uploading to PPA"
  exit 1
fi
