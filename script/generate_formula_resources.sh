#!/bin/bash
set -e

poetry export -f requirements.txt --without-hashes -o deps.txt

RESOURCES=""

while read -r dep; do
  [[ "$dep" =~ ^#.*$ ]] && continue
  [[ -z "$dep" ]] && continue

  if [[ "$dep" =~ ^([^=<>!]+)==([^;]+) ]]; then
    PKG_NAME="${BASH_REMATCH[1]}"
    VERSION="${BASH_REMATCH[2]}"
    VERSION=$(echo "$VERSION" | xargs)
  else
    echo "Skipping invalid dependency format: $dep" >&2
    continue
  fi

  JSON=$(curl -s "https://pypi.org/pypi/${PKG_NAME}/json")

  # Homebrew's virtualenv_install_with_resources installs from extracted archives,
  # so sdist (source) is required — wheels are zip files that pip cannot install
  # from a directory. With `depends_on "rust" => :build` in the formula, packages
  # like rpds-py that need maturin can compile from source.
  RELEASE_DATA=$(echo "$JSON" | jq -rc ".releases[\"$VERSION\"][]? | select(.packagetype == \"sdist\")" | head -1)

  # Fall back to wheel only for packages that ship no sdist at all
  if [[ -z "$RELEASE_DATA" ]]; then
    RELEASE_DATA=$(echo "$JSON" | jq -rc ".releases[\"$VERSION\"][]? | select(.packagetype == \"bdist_wheel\")" | head -1)
  fi

  if [[ -z "$RELEASE_DATA" ]]; then
    echo "Warning: No distribution found for $PKG_NAME $VERSION" >&2
    continue
  fi

  URL=$(echo "$RELEASE_DATA" | jq -r '.url')
  SHA256=$(echo "$RELEASE_DATA" | jq -r '.digests.sha256')

  RESOURCES+="  resource \"$PKG_NAME\" do
    url \"$URL\"
    sha256 \"$SHA256\"
  end
"

done < deps.txt

echo "$RESOURCES"

rm deps.txt
