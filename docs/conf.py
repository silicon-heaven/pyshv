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
    "sphinx_mdinclude",
    "sphinx_multiversion",
]

templates_path = ["_templates"]
exclude_patterns = ["_build"]
locale_dirs = []  # type: ignore

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


autodoc_member_order = "bysource"
autodoc_typehints = "description"
# autodoc_typehints = "none"
autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
autodoc_type_aliases = {
    "SHVType": "shv.SHVType",
    "shv.SHVType": "shv.SHVType",
    "shv.value.SHVType": "shv.SHVType",
    "SHVNullType": "shv.SHVNullType",
    "SHVBoolType": "shv.SHVBoolType",
    "SHVListType": "shv.SHVListType",
    "SHVMapType": "shv.SHVMapType",
    "SHVIMapType": "shv.SHVIMapType",
    "SHVMetaType": "shv.SHVMetaType",
    "SHVMethodT": "shv.rpcapi.methods.SHVMethodT",
    "SHVGetMethodT": "shv.rpcapi.methods.SHVGetMethodT",
    "SHVSetMethodT": "shv.rpcapi.methods.SHVSetMethodT",
    "SHVTypeBitfieldCompatible": "shv.rpctypes.SHVTypeBitfieldCompatible",
    "RpcTypeBitfieldCompatible": "shv.rpctypes.RpcTypeBitfieldCompatible",
}


intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "websockets": ("https://websockets.readthedocs.io/en/stable/", None),
    "can": ("https://python-can.readthedocs.io/en/stable/", None),
}
nitpick_ignore = {
    # These are undocumented in upstream Python documentation
    ("py:class", "asyncio.streams.StreamReader"),
    ("py:class", "asyncio.streams.StreamWriter"),
    ("py:class", "weakref.ReferenceType"),
    ("py:class", "weakref.WeakValueDictionary"),
    ("py:obj", "typing.T"),
    # This is not type but generic type alias
    ("py:class", "T"),
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
    """Resolve some references that Sphinx gets wrong."""
    if node["refdomain"] != "py":
        return
    domain = app.env.get_domain("py")
    target = node["reftarget"]
    # These are types that are inferred as class
    for n, v in autodoc_type_aliases.items():
        if target.endswith(f".{n}") or target == n:
            return domain.resolve_xref(
                env, node["refdoc"], app.builder, "type", v, node, contnode
            )
    # These are wrong for some reason
    name_map = {
        "asyncio.queues.Queue": "asyncio.Queue",
        "asyncio.locks.Lock": "asyncio.Lock",
        "_asyncio.Task": "asyncio.Task",
        "_asyncio.Future": "asyncio.Future",
    }
    if (rename := name_map.get(target)) is not None:
        node["reftarget"] = rename
        node["refspecific"] = False


def setup(app):  # type: ignore
    app.connect("build-finished", build_finished_gitignore)
    # Run before intersphinx to resolve our name rewrites above.
    app.connect("missing-reference", resolve_type_aliases, priority=400)
