"""pySHV version."""
import pathlib

__version__ = (pathlib.Path(__file__).parent / "version").read_text("utf-8").strip()
