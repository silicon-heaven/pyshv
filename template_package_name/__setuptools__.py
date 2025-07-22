"""Setuptools hook used to replace __version__.py file."""

import pathlib

from setuptools.command.build_py import build_py as _build_py


class BuildPy(_build_py):
    """Custom package build step."""

    def run(self) -> None:  # noqa: D102
        package = pathlib.Path(__file__).parent.name
        buildlib = pathlib.Path(self.build_lib) / package
        buildlib.mkdir(parents=True, exist_ok=True)
        version = self.distribution.metadata.version
        (buildlib / "__version__.py").write_text(f'VERSION = "{version}"\n')
        super().run()
        (buildlib / "__setuptools__.py").unlink()
