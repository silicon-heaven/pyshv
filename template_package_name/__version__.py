"""The loader of the version for source file only installation.

It looks for pyproject.toml file in upper directory and loads version from
there.

This file is overwritten during distribution build to contain only constant
VERSION. Please see __setuptools__.py for details.
"""

import pathlib
import tomllib


def _get_version() -> str:
    pyproject = pathlib.Path(__file__).parents[1] / "pyproject.toml"
    if pyproject.exists():
        with pyproject.open("rb") as f:
            res = tomllib.load(f)["project"]["version"]
            if isinstance(res, str):
                return res
    return "unknown"


VERSION = _get_version()
