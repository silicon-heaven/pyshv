# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path("..").absolute()))

project = "Elektroline Python project Template"
copyright = "2023, Elektroline a.s."
author = "Elektroline a.s."


extensions = [
    "sphinx.ext.doctest",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.todo",
    "sphinx_rtd_theme",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

# html_logo = "_static/logo.svg"
# html_favicon = "_static/favicon.ico"
html_copy_source = True
html_show_sourcelink = True
html_show_copyright = False
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]


autodoc_typehints = "description"
autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}


intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}
