#!/bin/bash
set -euo pipefail

# === Configuration ===
export VERSION="2.0.0b13"
export SOURCE_FILE="jpipe-runner.tar.gz"
export CLASS_NAME="JpipeRunner"
export HOMEPAGE_URL="https://github.com/jpipe-mcscert/jpipe-runner"
export SOURCE_URL="https://github.com/jpipe-mcscert/jpipe-runner/releases/download/v2.0.0b8/jpipe_runner-${VERSION}.tar.gz"
export SOURCE_SHA256="37b161961d412e68526df7310b9580de320aab485070789cdc30e872559467c3"
export PYTHON_VERSION="3.11"

# === Create destination directory ===
mkdir -p tap/Formula

###############
# Without GUI #
###############

# Generate Homebrew resource blocks using external script
export RESOURCES="$(bash script/generate_formula_resources.sh)"

# Generate main formula file
envsubst < Formula/homebrew_formula_template.rb > tap/Formula/jpipe-runner.rb

echo "Generated formula file at tap/Formula/jpipe-runner.rb"

# Generate versioned formula file
export FORMATTED_VERSION=$(echo "$VERSION" | sed 's/\.//g')

# Generate versioned formula (without GUI)
export CLASS_NAME="${CLASS_NAME}AT${FORMATTED_VERSION}"

# Generate versioned formula file
envsubst < Formula/homebrew_formula_template.rb > tap/Formula/jpipe-runner@$VERSION.rb

echo "Generated versioned formula file at tap/Formula/jpipe-runner@$VERSION.rb"

###############
#   With GUI  #
###############

# Define Formula class name for GUI version
export CLASS_NAME="JpipeRunnerGui"

# Generate GUI formula (with matplotlib/Tkinter)
export RESOURCES="$(bash script/generate_formula_resources.sh --with-gui)"

# Generate GUI formula file
envsubst < Formula/homebrew_formula_gui_template.rb > tap/Formula/jpipe-runner-gui.rb

echo "Generated GUI formula file at tap/Formula/jpipe-runner-gui.rb"

# Generate versioned GUI formula file
export CLASS_NAME="${CLASS_NAME}AT${FORMATTED_VERSION}"

# Generate versioned GUI formula file
envsubst < Formula/homebrew_formula_gui_template.rb > tap/Formula/jpipe-runner-gui@$VERSION.rb

echo "Generated versioned GUI formula file at tap/Formula/jpipe-runner-gui@$VERSION.rb"
