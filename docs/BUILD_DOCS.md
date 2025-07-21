# jpipe-runner Documentation 📚

This project uses **Sphinx** to generate documentation from reStructuredText (`.rst`) and optionally Markdown using MyST. Here's how to set it up and update the docs.

---

## 🛠️ Prerequisites

Make sure you have the following installed:

* Python (≥3.10)
* [Sphinx](https://www.sphinx-doc.org/en/master/usage/installation.html#pypi-package):

To build the documentation locally, install the optional `docs` dependencies:

```bash
pip install .[docs]
```

---

## 🧭 Project Structure

```
docs/python_docs/
└── source/
    ├── conf.py            ← Sphinx config
    ├── index.rst          ← Root toctree
    ├── modules.rst        ← API modules index
    ├── jpipe_runner.rst   ← Modules documentation
    └── ...
```

Your Python project lives in `src/jpipe_runner`, and Sphinx imports it via:

```python
# in /source/conf.py
import os, sys
sys.path.insert(0, os.path.abspath('../../../src'))
```

---

## 🚀 Generate or Update API Reference

Use `sphinx-apidoc` to auto-generate `.rst` stubs under `docs/python_docs/source/`:

```bash
cd docs/python_docs/
sphinx-apidoc -o source ../../src/jpipe_runner
```

This makes `.rst` files with `.. automodule::` directives for each module.

---

## 📝 Edit `index.rst`

Ensure your `index.rst` includes a `toctree` listing all pages, for instance:

```rst
jpipe‑runner Documentation
===========================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   jpipe_runner
   jpipe_runner.framework
   jpipe_runner.framework.decorators
   modules

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
```

This enables easy navigation via sidebar links and supports search.

---

## 📦 Build the Docs

From root:

```bash
cd docs/python_docs/
make singlehtml
```

Or directly:

```bash
sphinx-build -b singlehtml docs/python_docs/source docs/python_docs/build/singlehtml
```

Your generated site will be under `docs/build/html/`.

---

## 🔄 Updating Docs

1. **Add or edit module docstrings** in `src/jpipe_runner/...`.
2. If you add new modules, regenerate `.rst` files:

   ```bash
   cd docs/python_docs/
   sphinx-apidoc -o source ../../src/jpipe_runner
   ```
3. Adjust `index.rst` or other `.rst` pages to include new modules.
4. Rebuild HTML with `make html`.

---

## ✅ Extend Sphinx

* Add extensions to `conf.py`, e.g.:

  ```python
  extensions = [
      'sphinx.ext.autodoc',
      'sphinx.ext.napoleon',
      'sphinx.ext.viewcode',
      'myst_parser',         # Markdown support
  ]

  source_suffix = {
      '.rst': 'restructuredtext',
      '.md': 'markdown',
  }

  html_theme = 'sphinx_rtd_theme'
  ```

* Use directives like `.. automodule::`, `.. autoclass::`, or `.. autosummary::` in your `.rst` files.

* Insert Markdown content via MyST or include assets.

---

## 📚 Learn More

* **Sphinx Quickstart & reStructuredText** essentials ([quickstart][1], [docutils][2], [restructuredtext][3])
* **Markdown support (MyST Parser)** ([markdown][4])

[1]: https://www.sphinx-doc.org/en/master/usage/quickstart.html#setting-up-the-documentation-sources "Getting started - Sphinx documentation"
[2]: https://docutils.sourceforge.io/rst.html "reStructuredText support - docutils documentation"
[3]: https://www.sphinx-doc.org/en/master/usage/restructuredtext/index.html "reStructuredText Markup - Sphinx documentation"
[3]: https://www.sphinx-doc.org/en/master/usage/markdown.html "Markdown support - Sphinx documentation"
