#!/bin/bash

set -e

# Ensure the script is run from the project root
if [ ! -f "setup.py" ]; then
  echo "This script must be run from the project root directory."
  exit 1
fi

# Install necessary dependencies
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

# Generate Debian package structure
python3 setup.py --command-packages=stdeb.command sdist_dsc

# Build the .deb package
cd deb_dist/jpipe-runner-*
debuild -us -uc

# Upload to PPA
# dput ppa:yourusername/ppa ../jpipe-runner_2.0.0-1_source.changes

echo "Package has been uploaded to your PPA."
