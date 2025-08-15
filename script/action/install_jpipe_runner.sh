#!/usr/bin/env bash
set -euo pipefail

# Required env vars:
#   PYTHON_PATH          # Path to Python interpreter
#   VERSION              # Version of jpipe-runner to install (default: main)

PYTHON_PATH="${PYTHON_PATH:-python}"
VERSION="${VERSION:-main}"

if poetry env info --path &>/dev/null; then
  echo "Using Poetry"
  poetry add "git+https://github.com/jpipe-mcscert/jpipe-runner.git@${VERSION}"
else
  echo "Using pip"
  $PYTHON_PATH -m pip install -U "git+https://github.com/jpipe-mcscert/jpipe-runner.git@${VERSION}"
fi
