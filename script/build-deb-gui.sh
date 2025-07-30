#!/bin/bash

set -e

DEBFULLNAME="$1"; shift
DEBEMAIL="$1"; shift
GPG_ID="$1"; shift

DISTROS=("jammy" "noble")

echo "=== START build-deb-gui.sh (GUI) ==="

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
  lintian

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
echo ">>> Cleaning GUI build artifacts"
rm -rf deb_dist_gui/ dist/ ./*.tar.gz 2>/dev/null || true

# --- 5. Create temporary copies for GUI package ---
echo ">>> Creating temporary files for GUI package"

# Backup original files
cp setup.py setup.py.bak
cp stdeb.cfg stdeb.cfg.bak 2>/dev/null || true

# Create GUI-specific setup.py
sed 's/name="jpipe-runner"/name="jpipe-runner-gui"/' setup.py.bak > setup-gui.py
sed -i 's/"jpipe-runner = jpipe_runner.runner:main"/"jpipe-runner-gui = jpipe_runner.runner:main"/' setup-gui.py
sed -i "s/read_requirements()/read_requirements('requirements-gui.txt')/" setup-gui.py

# Create GUI-specific stdeb.cfg
if [[ -f stdeb.cfg.bak ]]; then
  cp stdeb.cfg.bak stdeb-gui.cfg
  sed -i '/^Depends=/ s/$/, python3-matplotlib/' stdeb-gui.cfg
else
  echo "Depends: python3-matplotlib" > stdeb-gui.cfg
fi

# --- 6. Extract version ---
VERSION=$(python3 setup-gui.py --version)
echo ">>> Detected version: $VERSION"

pip install --upgrade setuptools stdeb wheel

# --- 7. Build GUI Debian source package ---
echo ">>> Building GUI source package"
STDEB_CFG_FILE=stdeb-gui.cfg python3 setup-gui.py --command-packages=stdeb.command sdist_dsc --dist-dir=deb_dist_gui

# Find generated package directory
GUI_DIR=$(find deb_dist_gui -maxdepth 1 -type d -name "jpipe-runner-gui*" | head -n1)

# --- 8. Fix control, compat, rules ---
cd "$GUI_DIR"

echo "13" > debian/compat

CONTROL_FILE="debian/control"
if grep -q '^Build-Depends:' "$CONTROL_FILE"; then
  sed -i 's/^Build-Depends:.*/Build-Depends: debhelper (>= 10), dh-python, python3-all, python3-setuptools/' "$CONTROL_FILE"
else
  sed -i '1aBuild-Depends: debhelper (>= 10), dh-python, python3-all, python3-setuptools' "$CONTROL_FILE"
fi

sed -i 's/^Package: python3-jpipe-runner-gui/Package: jpipe-runner-gui/' "$CONTROL_FILE"

cat > debian/rules <<'EOF'
#!/usr/bin/make -f
%:
	dh $@ --with python3 --buildsystem=pybuild
EOF
chmod +x debian/rules

debsign -k "$GPG_ID" "../jpipe-runner-gui_${VERSION}-1_source.changes"

cd ../..

# --- 9. Build per-distro ---
for DISTRO in "${DISTROS[@]}"; do
  echo ">>> Building GUI for $DISTRO"

  DISTRO_DIR="deb_dist_gui/jpipe-runner-gui-${DISTRO}"
  cp -r "$GUI_DIR" "$DISTRO_DIR"

  pushd "$DISTRO_DIR"

  rm -f debian/changelog
  dch --create -v "${VERSION}-1~${DISTRO}1" --package jpipe-runner-gui --distribution "$DISTRO" "Build GUI package for $DISTRO"

  debuild -S -sa
  debsign -k "$GPG_ID" ../jpipe-runner-gui_${VERSION}-1~${DISTRO}1_source.changes

  # --- Run lintian checks ---
  echo ">>> Running lintian checks for GUI $DISTRO"
  CHANGES_FILE="../jpipe-runner-gui_${VERSION}-1~${DISTRO}1_source.changes"

  if [[ -f "$CHANGES_FILE" ]]; then
    echo "Checking: $CHANGES_FILE"
    lintian --pedantic --info --display-info --color=auto "$CHANGES_FILE" || {
      echo "WARNING: lintian found issues in $CHANGES_FILE"
      echo "Continuing build process..."
    }
  fi

  popd
done

# --- 10. Cleanup ---
echo ">>> Cleaning up GUI non-distro packages"
cd deb_dist_gui
find . -maxdepth 1 -type f \
  \( -name "jpipe-runner-gui_${VERSION}-1.dsc" \
     -o -name "jpipe-runner-gui_${VERSION}-1.debian.tar.*" \
     -o -name "jpipe-runner-gui_${VERSION}-1_source.*" \) \
  -exec rm -v {} +

echo ">>> Running final lintian checks on all GUI packages"
for changes_file in jpipe-runner-gui_*_source.changes; do
  if [[ -f "$changes_file" ]]; then
    echo "Final check: $changes_file"
    lintian --pedantic --info --display-info --color=auto "$changes_file" || true
  fi
done

cd ..

# --- 11. Restore original files ---
echo ">>> Restoring original files"
mv setup.py.bak setup.py
if [[ -f stdeb.cfg.bak ]]; then
  mv stdeb.cfg.bak stdeb.cfg
fi

# Clean up temporary files
rm -f setup-gui.py stdeb-gui.cfg

echo "=== build-deb-gui.sh (GUI) COMPLETED ==="
