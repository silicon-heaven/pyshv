"""Simple counter of strings of this package name."""

from .__version__ import VERSION
from .count import count_foo

__all__ = [
    "VERSION",
    "count_foo",
]
