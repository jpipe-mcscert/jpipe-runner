# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import os
import sys

sys.path.insert(0, os.path.abspath('../../../src'))

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'jpipe-runner'
copyright = '2025, Mosser Sébastien, Lyu Jason, Lacroix Baptiste'
author = 'Mosser Sébastien, Lyu Jason, Lacroix Baptiste'
release = '2.0.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',        # Pulls in docstrings :contentReference[oaicite:2]{index=2}
    'sphinx.ext.napoleon',       # Supports Google/NumPy style docstrings :contentReference[oaicite:3]{index=3}
    'sphinx.ext.viewcode',       # Adds links to source code
    'sphinx.ext.intersphinx',    # Cross-reference to external docs
    'sphinx.ext.coverage',
    'sphinx.ext.githubpages',
]

# Intersphinx mapping for common references
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}

# Autodoc settings
autodoc_member_order = 'bysource'
autodoc_typehints = 'description'

# Napoleon settings (from sphinx-autodoc-example) :contentReference[oaicite:4]{index=4}
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = False

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'alabaster'
html_static_path = ['_static']
