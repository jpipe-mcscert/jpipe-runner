# 📦 Packaging & Release Guide

## 🚀 Release Pipeline Overview

The CI/CD pipeline automated testing, packaging, and publishing to multiple platforms. It is defined in
`.github/workflows/release.yml` and triggered on GitHub tags.

## Pipeline

### 1. Dumping Python Version

When dumping the Python version, here all the files to update:

- `action.yml`:  Update python-version: "YOUR_PYTHON_VERSION"
- `release.yml`: Update the python-version environment variable
- `pyproject.toml`: Update the python version in the `[tool.poetry.dependencies]` section

## `action.yml`

The `action.yml` file defines the **composite GitHub Action** that automates the execution of justification diagrams
using `jpipe-runner`. It manages system and Python dependency setup,
runs the jPipe tool, collects the resulting diagrams, and integrates directly with GitHub issues or pull requests by
posting status comments and uploading artifacts.

## Key Features

#### 1. System Dependency Installation

`jpipe-runner` depends on **Graphviz** and related packages for diagram rendering. These are installed as part of the
action setup:

```yaml
sudo apt-get install -y graphviz libgraphviz-dev pkg-config
```

This ensures that all required native dependencies are available before running Python-based logic.

#### 2. Conditional Python Setup

If no `python_path` is provided, the action automatically sets up **Python 3.11** via `actions/setup-python@v5`. This
supports both minimal and advanced usage depending on project needs.

#### 3. Smart Dependency Management

The action supports **both Poetry and pip** installations:

* If a Poetry environment is detected, it installs `jpipe-runner` via Poetry for better dependency resolution.
* Otherwise, it falls back to pip for broader compatibility.

This dual-mode approach allows integration with both modern Python workflows and legacy setups.

#### 4. Continue-on-Error Strategy

```yaml
continue-on-error: true
```

The main execution step is allowed to fail without stopping the entire workflow. This ensures:

* Artifacts (e.g. partial diagram outputs) can still be uploaded
* GitHub comments can report failure details

#### 5. Artifact Management

```yaml
- uses: actions/upload-artifact@v4
  if: always()
```

Generated diagram files are always uploaded, whether the run succeeded or not. This provides visual output of the
justification diagram.

#### 6. GitHub Integration via Comments

The action automatically posts a comment on the pull request that triggered the workflow. The comment includes:

* A success/failure message
* A download link for the diagram artifact (if available)

This makes feedback visible directly in the GitHub UI, eliminating the need to manually open workflow logs.

#### 7. Steps `Fail if jpipe-runner failed`

This step checks the exit code of the `jpipe-runner` execution. If it is not `0`, it fails the workflow with a clear
error message.

### Environment Variables Usage

These environment variables are used to maintain consistent behavior across steps:

* **`PYTHON_PATH`**: Defines the Python executable used for installation and execution.
* **`working-directory`**: The base path for execution (matches user input or defaults to `.`, the current directory).
* **`OUTPUT_DIR`**: Internal path where diagram files are saved (used for file discovery and artifact upload).
* **`GITHUB_TOKEN`**: Required to post comments on PRs and issues via GitHub API.

### Output Variables

This action sets outputs that downstream workflow steps can access:

* **`result`**:
  Exit code of the `jpipe-runner` execution (`0` if successful).

* **`diagram_path`**:
  Full file path to the generated diagram.

* **`diagram_name`**:
  The filename (e.g. `justification.svg`) of the generated diagram.


## `release.yml`

- `secrets.GPG_PRIVATE_KEY`: Your GPG private key used for signing the package, associated with your Launchpad account.
- `secrets.DEBFULLNAME`: Your full name as it appears in your GPG key, used for signing the Debian package.
- `secrets.DEBEMAIL`: Your email address associated with your GPG key, used for signing the Debian package.
- `secrets.GPG_ID`: The GPG key ID used for signing the Debian package, which must match the key uploaded to Launchpad.
- `secrets.LAUNCHPAD_USERNAME`: Your Launchpad username, which must be associated with a GPG key that has been uploaded
  to Launchpad.
- `secrets.HOMEBREW_TAP_PAT`: Your GitHub Personal Access Token (PAT) for Homebrew tap repository access, so the
  GithubActionBot can push the Homebrew formula to the repository.

## 🔐 GPG for Launchpad PPA

### Why Use GPG?

GPG (GNU Privacy Guard) is used to **sign Debian source packages** before uploading them to a Launchpad PPA (Personal
Package Archive).

Launchpad **requires all uploads to be cryptographically signed** with a trusted GPG key associated with the Ubuntu or
Launchpad account.

Without a valid GPG signature, Launchpad will reject the upload attempt.

### How to set up GPG for Launchpad PPA

1. **Generate GPG key:**

```bash
gpg --full-generate-key
```

2. **Find your key ID:**

```bash
gpg --list-keys --keyid-format LONG
```

3. **Upload to Ubuntu Keyserver:**

```bash
gpg --keyserver hkp://keyserver.ubuntu.com:80 --send-keys <KEY_ID>
```

4. **Verify Key is Published:**
   [https://keyserver.ubuntu.com/pks/lookup?search=\<KEY\_ID>\&fingerprint=on\&op=index](https://keyserver.ubuntu.com/pks/lookup)

5. **Add to Launchpad:**
   [https://launchpad.net/~<username\>/+editpgpkeys](https://launchpad.net/~<username>/+editpgpkeys)

6. **Decrypt Launchpad Email Message:**
   Paste the PGP message into a file:

```bash
nano launchpad.asc
gpg --decrypt launchpad.asc
```

Click the link from the decrypted message to confirm.

## 🏗️ Build Debian Package (PPA)

For building the Debian package for PPA (Launchpad), we are using the stdeb library tool, which can generate .deb
file and folder architecture for Debian-based systems mandatory by Launchpad.

### 1. `sdist_dsc` command

For now, we are using the `sdist_dsc` command from the stdeb library to generate the Debian source package.
But this library is not maintained anymore, and we are looking for alternatives.
This is limited to Python 3.11 and below, that is blocking us from using recent Python versions.

### 2. `debian/control` file

When `sdist_dsc` is executed and the folder architecture and archives are generated.
At this point, we need to update the `debian/control` file to ensure it includes the correct build dependencies.
This step is essential to ensure that the package builds correctly on Launchpad, with all required tools and Python
components available.

### 3. `debian/rules` file

The `debian/rules` file is a **makefile** that defines how the package should be built by the Debian packaging system.
It is a critical part of the build process and is used by `dpkg-buildpackage` and other tools during package
compilation.

In our case, we generate a minimal `rules` file that delegates the build process to **debhelper** using the `pybuild`
build system. Here's what we do and why:

* We invoke `debhelper` (`dh`) with the `--with python3` option to ensure Python 3 support is included.
* The `--buildsystem=pybuild` option tells debhelper to use **pybuild**, which is the recommended build system for
  Python
* packages in Debian. It automatically handles Python versions, build directories, and setup script execution.

This setup ensures that the Python package is built in a way that is compliant with Debian standards

### 4. Sign source change files

After generating the Debian source package, we need to sign the source change files (`.dsc` and `.changes`) with GPG.
This is a crucial step for Launchpad PPA, as it verifies the authenticity of the package and its source.

### 5. Build for Different Distributions

To support multiple Ubuntu or Debian-based distributions (e.g. *jammy*, *noble*), we build a separate source
package for each target distro. This ensures compatibility and proper upload to corresponding PPAs on Launchpad.

Here’s what we do, and why:

* **Per-distro preparation:**
  For each distribution listed (e.g., in a `DISTROS` array), we create a separate build directory. This is done by
  copying the base source tree into a new folder named after the distribution. It isolates builds and avoids file
  conflicts.

* **Update the changelog with `dch`:**
  We remove any existing `debian/changelog` file and create a new one for each distribution using the `dch` (Debian
  ChangeLog) tool.
  The changelog entry includes:

    * A version string tailored to the distribution (e.g. `1.0.0-1~jammy1`)
    * The target distribution name
    * A message to specify for which distribution we are building it like "Build for jammy"

  This step is crucial because Launchpad uses the changelog to identify the target distribution and version of the
  package.

* **Build and sign the source package:**

    * `debuild -S -sa` is used to build a **source package** (`-S`) and include all source files (`-sa`).
      This is the format required for upload to Launchpad.
    * `debsign` is then used to cryptographically **sign** the source package using a GPG key.
      Launchpad requires this signature to verify the authenticity and integrity of the upload.

### Adding a new distribution

To add a new distribution to the build process, you need to add the distribution name to the `DISTROS`
array in the `build-deb.sh` and `build-deb-gui.sh` files.

```shell
DISTROS=("jammy" "noble")
```

### 6. Lintian checks

We are using **Lintian** to perform a checking and validation of the Debian package.
Lintian is a static analysis tool that checks Debian packages for common errors, policy violations, and best practices.

## Publishing to Launchpad PPA

After building the Debian source package, we upload it to Launchpad PPA using the `publish-ppa.sh` script.
The script needs a `LAUNCHPAD_USERNAME` and the `*.changes` files to upload.

- `LAUNCHPAD_USERNAME`: Your Launchpad username, which must be associated with a GPG key that has been uploaded to
  Launchpad.

## 🍺 Homebrew Formula

To generate our Homebrew formula, we use a Formula Template containing environment variables.
These variables are automatically populated by the GitHub Actions workflow during the release process.

### 1. Which variables are used, and why?

* `$CLASS_NAME`: The name of the formula’s class.
* `$HOMEPAGE_URL`: The URL of the GitHub repository.
* `$SOURCE_URL`: The URL of the source archive from the GitHub release.
* `$SOURCE_SHA256`: The SHA256 checksum of the source archive.
* `$PYTHON_VERSION`: The Python version required by the package.
* `$RESOURCES`: A list of required resources (e.g., dependencies), each with its specific version.

### 2. Resources

Resources are automatically generated by the `generate_formula_resources.sh` script.
This script uses Poetry to export the dependencies into a `requirements.txt` file, and then parses it to create the
resource list with exact versions.

### 3. `SOURCE_DATE_EPOCH` environment variable

The `SOURCE_DATE_EPOCH` environment variable is set to define the date and time for files generated during the formula
installation process.
This is required to avoid issues with ZIP file timestamps earlier than 1980, which can cause problems with `pip` and
dependency handling.
