"""Various tools used in the code."""

import collections.abc
import typing

T = typing.TypeVar("T")


def lookahead(
    iterin: collections.abc.Iterable[T],
) -> collections.abc.Iterator[tuple[T, bool]]:
    """Itearte and tell if there is more data comming."""
    it = iter(iterin)
    try:
        prev = next(it)
    except StopIteration:
        return
    for v in it:
        yield prev, True
        prev = v
    yield prev, False
