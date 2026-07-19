#!/usr/bin/env bash
set -euo pipefail

# Required env vars:
#   PYTHON_EXEC_PATH     # Path to Python interpreter
#   VERSION              # Version of jpipe-runner to install (default: main)

PYTHON_EXEC_PATH="${PYTHON_EXEC_PATH:-python}"
VERSION="${VERSION:-main}"

# Install quietly: -q/-qq suppress the routine progress chatter (Collecting…,
# Downloading…, Building wheel…) that otherwise floods the Actions log on every run.
# Warnings and errors are still printed, so a failed install remains diagnosable.
if poetry env info --path &>/dev/null; then
  echo "Using Poetry"
  poetry add -q "git+https://github.com/jpipe-mcscert/jpipe-runner.git@${VERSION}"
else
  echo "Using pip"
  $PYTHON_EXEC_PATH -m pip install -q -q -U \
    --disable-pip-version-check --no-input \
    "git+https://github.com/jpipe-mcscert/jpipe-runner.git@${VERSION}"
fi
echo "jpipe-runner installed (ref: ${VERSION})."
