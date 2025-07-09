#!/bin/bash

DEBFULLNAME="$1"; shift
DEBEMAIL="$1"; shift
GPG_ID="$1"; shift

echo "=== START build-deb.sh ==="
echo

# Install required tools
echo ">>> Installing system dependencies"
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    devscripts \
    debhelper \
    dh-python \
    python3-all \
    python3-setuptools \
    python3-pip

# Ensure stdeb is available
if ! pip3 show stdeb &>/dev/null; then
  echo ">>> Installing stdeb via pip"
  pip3 install --upgrade stdeb
else
  echo ">>> stdeb already installed"
fi
echo

# Export Debian signing env vars
echo ">>> Exporting DEBFULLNAME, DEBEMAIL, DEBSIGN_KEYID"
export DEBFULLNAME
export DEBEMAIL
export DEBSIGN_KEYID="$GPG_ID"
echo

# Clean previous builds
echo ">>> Cleaning old build artifacts"
rm -rf deb_dist/
rm -rf dist/ *.tar.gz
echo

# Build the source package
echo ">>> Building source package (stdeb sdist_dsc)"
python3 setup.py --command-packages=stdeb.command sdist_dsc
if [ $? -ne 0 ]; then
  echo "Error building source package"
  exit 1
fi
echo

# Change into the generated package directory
PKG_DIR=$(find deb_dist -maxdepth 1 -type d | tail -n1)
echo ">>> Entering source package dir: $PKG_DIR"
cd "$PKG_DIR" || {
  echo "Error changing directory to $PKG_DIR"
  exit 1
}
pwd
echo

# Build the Debian source upload (include original source)
echo ">>> Running debuild -S -sa"
debuild -S -sa
if [ $? -ne 0 ]; then
  echo "Error building Debian source package"
  exit 1
fi
echo

# Change back to the parent directory
cd ../

# Sign the .changes file
echo ">>> Signing .changes file with debsign"
debsign -k "$GPG_ID" *.changes
if [ $? -ne 0 ]; then
  echo "Error signing .changes file"
  exit 1
fi
echo
echo "=== build-deb.sh COMPLETED SUCCESSFULLY ==="
