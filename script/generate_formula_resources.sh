#!/bin/bash
set -e

if [[ "$1" == "--with-gui" ]]; then
    # Export requirements with GUI dependencies
    poetry export --extras gui -f requirements.txt --without-hashes -o deps.txt
else
    # Export base requirements
    poetry export -f requirements.txt --without-hashes -o deps.txt
fi

RESOURCES=""

while read -r dep; do
  # Skip comments and empty lines
  [[ "$dep" =~ ^#.*$ ]] && continue
  [[ -z "$dep" ]] && continue

  # Extract package name and version, handling Python version markers
  # Format: "package==version ; python_version >= "3.10""
  if [[ "$dep" =~ ^([^=<>!]+)==([^;]+) ]]; then
    PKG_NAME="${BASH_REMATCH[1]}"
    VERSION="${BASH_REMATCH[2]}"
    # Trim whitespace from version
    VERSION=$(echo "$VERSION" | xargs)
  else
    echo "Skipping invalid dependency format: $dep" >&2
    continue
  fi

  # Get package info from PyPI
  JSON=$(curl -s "https://pypi.org/pypi/${PKG_NAME}/json")

  # Try to get source distribution first
  RELEASE_DATA=$(echo "$JSON" | jq -r ".releases[\"$VERSION\"][]? | select(.packagetype == \"sdist\")")

  # If no sdist available, try wheel
  if [[ -z "$RELEASE_DATA" ]]; then
    RELEASE_DATA=$(echo "$JSON" | jq -r ".releases[\"$VERSION\"][]? | select(.packagetype == \"bdist_wheel\")")
  fi

  if [[ -z "$RELEASE_DATA" ]]; then
    echo "Warning: No distribution found for $PKG_NAME $VERSION" >&2
    continue
  fi

  URL=$(echo "$RELEASE_DATA" | jq -r '.url')
  SHA256=$(echo "$RELEASE_DATA" | jq -r '.digests.sha256')

  if [[ -n "$URL" && -n "$SHA256" ]]; then
    RESOURCES+="
  resource \"$PKG_NAME\" do
    url \"$URL\"
    sha256 \"$SHA256\"
  end
"
  fi

done < deps.txt

echo "$RESOURCES"

rm deps.txt
