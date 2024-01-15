"""Simple counter of strings of this package name."""
from .count import count_foo

VERSION = (
    (__import__("pathlib").Path(__file__).parent / "version").read_text("utf-8").strip()
)

__all__ = [
    "count_foo",
]
