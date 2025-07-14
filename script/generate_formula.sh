#!/bin/bash
set -e

# Set environment variables for envsubst
export CLASS_NAME="JpipeRunner"
export HOMEPAGE_URL="https://github.com/jpipe-mcscert/jpipe-runner"
export SOURCE_URL="https://github.com/jpipe-mcscert/jpipe-runner/releases/download/${TAG}/$(basename ${SOURCE_FILE})"
export SOURCE_SHA256="$SHA256"
export PYTHON_VERSION="3.10"

# Generate Homebrew resource blocks using external script
export RESOURCES="$(bash script/generate_formula_resources.sh)"

# Create destination directory
mkdir -p tap/Formula

# Use envsubst to generate final formula
envsubst < Formula/homebrew_formula_template.rb > tap/Formula/jpipe-runner.rb

echo "Generated formula file at tap/Formula/jpipe-runner.rb"
