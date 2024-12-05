"""Simple counter of strings of this package name.

This package is base for the packages to be implemented.
"""

from .__version__ import VERSION
from .count import count_foo

__all__ = [
    "VERSION",
    "count_foo",
]
