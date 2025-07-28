#!/bin/bash
set -e

# Export Poetry dependencies to deps.txt (no hashes)
poetry export -f requirements.txt --without-hashes -o deps.txt

RESOURCES=""

while read -r dep; do
  # Skip comments and empty lines
  [[ "$dep" =~ ^#.*$ ]] && continue
  [[ -z "$dep" ]] && continue

  # Extract package name (strip version specifiers, extras, spaces)
  PKG_NAME=$(echo "$dep" | sed -E 's/\[.*\]//; s/[<>=!].*//; s/ *//g')

  JSON=$(curl -s "https://pypi.org/pypi/${PKG_NAME}/json")

  # Get the latest .tar.gz release (source distribution)
  URL=$(echo "$JSON" | jq -r '.urls[] | select(.packagetype == "sdist") | .url')
  SHA256=$(echo "$JSON" | jq -r '.urls[] | select(.packagetype == "sdist") | .digests.sha256')

  if [[ -z "$URL" || -z "$SHA256" ]]; then
    continue
  fi

  RESOURCES+="
  resource \"$PKG_NAME\" do
    url \"$URL\"
    sha256 \"$SHA256\"
  end
"
done < deps.txt

echo "$RESOURCES"

rm deps.txt
