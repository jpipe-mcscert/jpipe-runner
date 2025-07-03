#!/bin/bash

set -e

# Ensure the script is run from the project root
if [ ! -f "setup.py" ]; then
  echo "This script must be run from the project root directory."
  exit 1
fi

sudo apt update
sudo apt install -y \
  build-essential \
  devscripts \
  debhelper \
  dh-python \
  python3-all \
  python3-setuptools \
  python3-stdeb \
  python3-pip

# Install stdeb if not already installed
pip3 show stdeb || pip3 install stdeb

# Create the Debian package
python setup.py --command-packages=stdeb.command bdist_deb
