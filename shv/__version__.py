"""The smarter loader of the version.

It identifies if this package is installed and returns version from egg info or
it looks for pyproject.toml file in upper directory.
"""

import importlib.metadata
import pathlib
import tomllib


def _get_version() -> str:
    for dist_name in importlib.metadata.packages_distributions().get(__package__, []):
        dist = importlib.metadata.distribution(dist_name)
        if str(dist.locate_file(f"{__package__}/__version__.py")) == __file__:
            return dist.version
    pyproject = pathlib.Path(__file__).parent.parent / "pyproject.toml"
    if pyproject.exists():
        with pyproject.open("rb") as f:
            res = tomllib.load(f)["project"]["version"]
            if isinstance(res, str):
                return res
    return "unknown"


VERSION = _get_version()
