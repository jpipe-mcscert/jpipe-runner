#!/bin/bash
set -euo pipefail

# === Configuration ===
export SOURCE_FILE="jpipe-runner.tar.gz"
export CLASS_NAME="JpipeRunner"
export HOMEPAGE_URL="https://github.com/jpipe-mcscert/jpipe-runner"
export SOURCE_URL="https://github.com/jpipe-mcscert/jpipe-runner/releases/download/v2.0.0b8/jpipe_runner-2.0.0b8.tar.gz"
export SOURCE_SHA256="37b161961d412e68526df7310b9580de320aab485070789cdc30e872559467c3"
export PYTHON_VERSION="3.10"
export VERSION="2.0.0b8"


# transform version to match Homebrew format
export FORMATTED_VERSION=$(echo "$VERSION" | sed 's/\.//g')

# === Create destination directory ===
mkdir -p tap/Formula

# === Generate final formula using envsubst ===
envsubst < Formula/homebrew_formula_template.rb > tap/Formula/jpipe-runner.rb
export CLASS_NAME="${CLASS_NAME}AT${FORMATTED_VERSION}"
envsubst < Formula/homebrew_formula_template.rb > tap/Formula/jpipe-runner@$VERSION.rb

echo "Generated formula file at tap/Formula/jpipe-runner.rb"
