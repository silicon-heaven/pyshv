# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path("..").absolute()))

project = "Silicon Heaven in Python"
copyright = "SPDX-License-Identifier: MIT"
author = "Elektroline a.s."


extensions = [
    "sphinx.ext.doctest",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.todo",
    "sphinx_book_theme",
    "sphinx_multiversion",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]

html_logo = "_static/logo.svg"
html_favicon = "_static/favicon.ico"
html_copy_source = True
html_show_sourcelink = True
html_show_copyright = False
html_theme = "sphinx_book_theme"
html_static_path = ["_static"]
html_sidebars = {
    "**": [
        "navbar-logo.html",
        "icon-links.html",
        "search-button-field.html",
        "sbt-sidebar-nav.html",
        "versioning.html",
    ]
}
html_theme_options = {
    "show_toc_level": 3,
    "repository_url": "https://gitlab.com/silicon-heaven/pyshv",
    "repository_branch": "master",
    "path_to_docs": "docs",
    "use_source_button": True,
    "use_repository_button": True,
    "use_edit_page_button": True,
    "use_issues_button": True,
}


# Sphinx has issues with type aliases. We want them to be referenced but it
# instead expands them. This is hack to convince him to correcly link them.
type_vars = {
    "SHVType",
    "SHVNullType",
    "SHVBoolType",
    "SHVListType",
    "SHVMapType",
    "SHVIMapType",
    "SHVMetaType",
    "SHVMethodT",
    "SHVGetMethodT",
    "SHVSetMethodT",
    "NamedT",
}

autodoc_member_order = "bysource"
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_type_aliases = {
    "shv.rpcerrors.RpcError": "shv.RpcError",
    "shv.rpcerrors.RpcErrorCode": "shv.RpcErrorCode",
    **{v: v for v in type_vars},
}


intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "websockets": ("https://websockets.readthedocs.io/en/stable/", None),
}
nitpick_ignore = {
    # These are undocumented in upstread Python documentation
    ("py:class", "asyncio.streams.StreamReader"),
    ("py:class", "asyncio.streams.StreamWriter"),
    ("py:class", "weakref.ReferenceType"),
    ("py:class", "dataclasses.InitVar"),
}

smv_tag_whitelist = r"^v.*$"
smv_branch_whitelist = r"^master$"
smv_remote_whitelist = r"^.*$"


def build_finished_gitignore(app, exception):  # type: ignore
    """Create .gitignore file when build is finished."""
    outpath = pathlib.Path(app.outdir)
    if exception is None and outpath.is_dir():
        (outpath / ".gitignore").write_text("**\n")


def resolve_type_aliases(app, env, node, contnode):  # type: ignore
    """Resolve :class: references to our type aliases as :attr: instead."""
    if node["refdomain"] == "py" and node["reftarget"] in type_vars:
        return app.env.get_domain("py").resolve_xref(
            env, node["refdoc"], app.builder, "data", node["reftarget"], node, contnode
        )


def setup(app):  # type: ignore
    app.connect("build-finished", build_finished_gitignore)
    app.connect("missing-reference", resolve_type_aliases)
