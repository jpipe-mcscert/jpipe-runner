#!/bin/bash

set -e

DEBFULLNAME="$1"; shift
DEBEMAIL="$1"; shift
GPG_ID="$1"; shift

DISTROS=("jammy" "noble")

echo "=== START build-deb.sh ==="

# --- 1. Dependencies ---
echo ">>> Installing build dependencies"
sudo apt-get update
sudo apt-get install -y \
  build-essential \
  devscripts \
  debhelper \
  dh-python \
  python3-all \
  python3-setuptools \
  python3-pip \
  python3-distutils

# --- 2. Install stdeb if needed ---
if ! pip3 show stdeb &>/dev/null; then
  echo ">>> Installing stdeb via pip"
  pip3 install --upgrade stdeb
else
  echo ">>> stdeb already installed"
fi

# --- 3. Environment ---
export DEBFULLNAME
export DEBEMAIL
export DEBSIGN_KEYID="$GPG_ID"

# --- 4. Clean previous builds ---
echo ">>> Cleaning build artifacts"
rm -rf deb_dist/ dist/ ./*.tar.gz 2>/dev/null || true

# --- 5. Extract version from setup.py ---
VERSION=$(python3 setup.py --version)
echo ">>> Detected version: $VERSION"

pip install --upgrade setuptools stdeb wheel

# --- 6. Build base Debian source package ---
# FIXME: https://github.com/astraw/stdeb?tab=readme-ov-file#sdist-dsc-distutils-command
# FIXME: https://manpages.ubuntu.com/manpages/questing/en/man1/lintian.1.html
echo ">>> Building base source package"
python3 setup.py --command-packages=stdeb.command sdist_dsc

# Find generated package directory (e.g., deb_dist/jpipe-runner-2.0.0b5)
BASE_DIR=$(find deb_dist -maxdepth 1 -type d -name "jpipe-runner*" | head -n1)

# --- 7. Fix control, compat, rules (once in base dir) ---
cd "$BASE_DIR"

echo "13" > debian/compat

CONTROL_FILE="debian/control"
if grep -q '^Build-Depends:' "$CONTROL_FILE"; then
  sed -i 's/^Build-Depends:.*/Build-Depends: debhelper (>= 10), dh-python, python3-all, python3-setuptools/' "$CONTROL_FILE"
else
  sed -i '1aBuild-Depends: debhelper (>= 10), dh-python, python3-all, python3-setuptools' "$CONTROL_FILE"
fi

# Rename binary package if needed
sed -i 's/^Package: python3-jpipe-runner/Package: jpipe-runner/' "$CONTROL_FILE"

# Create debian/rules using pybuild
cat > debian/rules <<'EOF'
#!/usr/bin/make -f
%:
	dh $@ --with python3 --buildsystem=pybuild
EOF
chmod +x debian/rules

# Sign base source changes file
debsign -k "$GPG_ID" "../jpipe-runner_${VERSION}-1_source.changes"

cd ../..

# --- 8. Build per-distro ---
for DISTRO in "${DISTROS[@]}"; do
  echo ">>> Building for $DISTRO"

  DISTRO_DIR="deb_dist/jpipe-runner-${DISTRO}"
  cp -r "$BASE_DIR" "$DISTRO_DIR"

  pushd "$DISTRO_DIR"

  # Clean changelog and add a new entry per distro
  rm -f debian/changelog
  dch --create -v "${VERSION}-1~${DISTRO}1" --package jpipe-runner --distribution "$DISTRO" "Build for $DISTRO"

  # Build and sign
  debuild -S -sa
  debsign -k "$GPG_ID" ../jpipe-runner_${VERSION}-1~${DISTRO}1_source.changes

  popd
  echo
done

# --- 9. Cleanup: remove default/unstable artifacts ---
echo ">>> Cleaning up non-distro packages"
cd deb_dist
find . -maxdepth 1 -type f \
  \( -name "jpipe-runner_${VERSION}-1.dsc" \
     -o -name "jpipe-runner_${VERSION}-1.debian.tar.*" \
     -o -name "jpipe-runner_${VERSION}-1_source.*" \) \
  -exec rm -v {} +

echo "=== build-deb.sh COMPLETED SUCCESSFULLY ==="
