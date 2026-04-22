#!/bin/bash
set -e

poetry export -f requirements.txt --without-hashes -o deps.txt

RESOURCES=""

# Return the first JSON object matching a jq filter from $JSON for $VERSION
first_release() {
  echo "$JSON" | jq -rc ".releases[\"$VERSION\"][]? | select($1)" | head -1
}

resource_block() {
  local name="$1" data="$2"
  local url sha256
  url=$(echo "$data" | jq -r '.url')
  sha256=$(echo "$data" | jq -r '.digests.sha256')
  printf '  resource "%s" do\n    url "%s"\n    sha256 "%s"\n  end\n' "$name" "$url" "$sha256"
}

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

  # 1. Pure Python wheel (works on all platforms)
  DATA=$(first_release '(.packagetype == "bdist_wheel") and (.filename | test("(py3|py2\\.py3)-none-any"))')
  if [[ -n "$DATA" ]]; then
    RESOURCES+="$(resource_block "$PKG_NAME" "$DATA")"$'\n'
    continue
  fi

  # 2. Universal macOS wheel (works on both arm64 and x86_64)
  DATA=$(first_release '(.packagetype == "bdist_wheel") and (.filename | test("cp311.*macosx.*universal2"))')
  if [[ -n "$DATA" ]]; then
    RESOURCES+="$(resource_block "$PKG_NAME" "$DATA")"$'\n'
    continue
  fi

  # 3. Architecture-specific macOS wheels — emit on_arm / on_intel blocks
  ARM_DATA=$(first_release '(.packagetype == "bdist_wheel") and (.filename | test("cp311.*macosx.*arm64"))')
  INTEL_DATA=$(first_release '(.packagetype == "bdist_wheel") and (.filename | test("cp311.*macosx.*x86_64"))')

  if [[ -n "$ARM_DATA" || -n "$INTEL_DATA" ]]; then
    if [[ -n "$ARM_DATA" ]]; then
      RESOURCES+="  on_arm do"$'\n'
      RESOURCES+="$(resource_block "$PKG_NAME" "$ARM_DATA" | sed 's/^/  /')"$'\n'
      RESOURCES+="  end"$'\n'
    fi
    if [[ -n "$INTEL_DATA" ]]; then
      RESOURCES+="  on_intel do"$'\n'
      RESOURCES+="$(resource_block "$PKG_NAME" "$INTEL_DATA" | sed 's/^/  /')"$'\n'
      RESOURCES+="  end"$'\n'
    fi
    continue
  fi

  # 4. Fall back to sdist
  DATA=$(first_release '.packagetype == "sdist"')
  if [[ -n "$DATA" ]]; then
    echo "Warning: Using sdist for $PKG_NAME $VERSION (no macOS wheel available)" >&2
    RESOURCES+="$(resource_block "$PKG_NAME" "$DATA")"$'\n'
    continue
  fi

  echo "Warning: No distribution found for $PKG_NAME $VERSION" >&2

done < deps.txt

echo "$RESOURCES"

rm deps.txt
