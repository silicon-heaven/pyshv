"""Just some utilities we use in broker."""

from __future__ import annotations

import abc
import collections.abc
import itertools
import typing


class Comparable(typing.Protocol):
    """Protocol for annotating comparable types."""

    @abc.abstractmethod
    def __gt__(self: T, other: T) -> bool:
        pass

    @abc.abstractmethod
    def __lt__(self: T, other: T) -> bool:
        pass


T = typing.TypeVar("T", bound=Comparable)


def nmin(*vals: collections.abc.Iterator[T | None] | T | None) -> T | None:
    """Get minimum or ``None`` if all values were ``None``."""
    res: T | None = None
    itr = (v if isinstance(v, collections.abc.Iterator) else iter([v]) for v in vals)
    for val in itertools.chain(*itr):
        if val is not None and (res is None or res < val):
            res = val
    return res


def nmax(*vals: collections.abc.Iterator[T | None] | T | None) -> T | None:
    """Get maximum or ``None`` if all values were ``None``."""
    res: T | None = None
    itr = (v if isinstance(v, collections.abc.Iterator) else iter([v]) for v in vals)
    for val in itertools.chain(*itr):
        if val is not None and (res is None or res > val):
            res = val
    return res
