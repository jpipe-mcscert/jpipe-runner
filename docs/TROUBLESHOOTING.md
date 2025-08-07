# jPipe Runner — Troubleshooting Guide

This guide helps you resolve common errors and issues encountered when setting up or running **jPipe Runner** and its dependencies on different platforms.

## 1. Python Environment Issues

### Common problems

* Python version incompatible (requires Python 3.10+)
* Conflicts with multiple Python versions installed
* Missing Python packages
* Package installation and environment management issues

### Solutions

* **Check Python version**:

  ```bash
  python --version
  ```

* **Use virtual environments** (recommended):

  ```bash
  python -m venv venv
  source venv/bin/activate  # Linux/macOS
  venv\Scripts\activate     # Windows
  ```

* **Use Poetry** for dependency management:

  ```bash
  poetry install
  poetry shell
  ```

* On Windows, if Python isn’t recognized, check that Python is added to your system PATH.

## 2. Python Package and Library Issues

### Common Problems and Cross-Platform Fixes

| **Library**  | **Issue**                                                              | **Fix (Linux/macOS)**                                                                                                                                                                                                        | **Fix (Windows)**                                                                                                                                                                                                         |
|--------------|------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `poetry`     | Command not found, or dependency resolution fails                      | **Install Poetry:**<br>`curl -sSL https://install.python-poetry.org`                                                                                                                                                         | **Windows (Powershell)**:<br>`(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content \| py -` <br>After installation, add Poetry to your PATH and restart your terminal.                     |
| `tkinter`    | `ModuleNotFoundError: No module named '_tkinter'` or GUI not launching | **Debian/Ubuntu:** `sudo apt-get install python3-tk`<br>**macOS:** `brew install python-tk`                                                                                                                                  | **Windows:** Tkinter is bundled with the official Python installer.<br>If using Anaconda: `conda install tk`                                                                                                              |
| `graphviz`   | CLI tools not found or diagram generation fails                        | **Install CLI (Debian/Ubuntu):**<br>`sudo apt-get install graphviz libgraphviz-dev pkg-config build-essential python3-dev`<br>**Install CLI (macOS):**<br>`brew install graphviz`<br>**Python Bindings:** `pip install graphviz`<br>**Verify:** `dot -V` | **Install CLI:**<br>Download from [https://graphviz.org/download/](https://graphviz.org/download/)<br>Add Graphviz `bin` directory to your `PATH`.<br>**Python Bindings:** `pip install graphviz`<br>**Verify:** `dot -V` |
| `networkx`   | `ModuleNotFoundError`                                                  | `pip install networkx` or `poetry add networkx`                                                                                                                                                                              | Same as Linux/macOS                                                                                                                                                                                                       |
| `matplotlib` | Backend errors or missing GUI dependencies                             | `sudo apt-get install python3-tk python3-pyqt5` (Debian/Ubuntu)<br>Optionally, configure the Matplotlib backend manually (e.g., `Agg`, `TkAgg`, `Qt5Agg`).                                                                   | Matplotlib usually works out of the box. If issues arise, install missing GUI toolkits or set backend using `matplotlib.use('Agg')` in scripts.                                                                           |

## 3. Operating System and Toolchain Issues

### GPG (GNU Privacy Guard)

* **Common problems:**

  * GPG not installed or not found in PATH
  * Signing errors during release or packaging

* **Solutions:**

  * **Install GPG:**

    * Linux:

      ```bash
      sudo apt-get install gnupg
      ```

    * macOS:

      ```bash
      brew install gnupg
      ```

    * Windows:

      * Install Gpg4win from [https://gpg4win.org/](https://gpg4win.org/)
      * Add GPG binaries to PATH if needed

  * Ensure your keyring is properly configured for signing.

## 4. Packaging Tools

### a) **stdeb** (Debian package builder)

* **Linux (Debian/Ubuntu):**

  ```bash
  sudo apt-get install python3-stdeb
  ```

* On other platforms, `stdeb` is less commonly used; prefer Poetry or platform-specific packaging.

### b) **Homebrew (macOS)**

* To build or install Homebrew formula dependencies:

  ```bash
  brew install <package>
  ```

## 5. Testing Tools

### Pytest Issues

* **Common problems:**

  * Tests fail to discover modules
  * Missing dependencies or fixtures

* **Fixes:**

  * Run tests inside the Poetry environment:

    ```bash
    poetry run pytest
    ```

  * Check for missing test dependencies or update `pytest.ini`.

## 6. Platform-Specific Notes

| Platform    | Tips                                                                                                                                                                        |
|-------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Windows** | - Use official Python from python.org for best compatibility.<br>- Add all installed tools to PATH.<br>- Use PowerShell or WSL for a better shell experience.               |
| **Linux**   | - Use native package managers (apt, yum) to install dependencies.<br>- Use virtualenv or Poetry for Python isolation.                                                       |
| **macOS**   | - Use Homebrew to install system dependencies.<br>- Use Python 3 installed via Homebrew for best compatibility.<br>- GUI apps may require permissions or security settings. |

## 7. General Troubleshooting Tips

* Always check your environment variables, especially PATH.
* Use verbose flags (`--verbose` or `-V`) for more debug info.
* Restart terminals/IDEs after installing new software or modifying PATH.
* Consult official docs for any tool or dependency for latest updates.
* If you encounter permission errors, try running with elevated privileges or adjust file permissions.
