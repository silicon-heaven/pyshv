"""The SHV RPC type struct."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVIMapType, SHVType
from .base import RpcType


class RpcTypeStruct(RpcType, collections.abc.Mapping[int, tuple[RpcType, str]]):
    """The Struct type representation."""

    def __init__(
        self, items: collections.abc.Mapping[int, tuple[RpcType, str]]
    ) -> None:
        if len(items) != len(set(v[1] for v in items.values())):
            raise ValueError("Duplicate keys are not allowed")
        self._items = items
        self._index = {v[1]: k for k, v in items.items()}

    def key(self, key: str) -> int:
        """Convert string key to integer key."""
        return self._index[key]

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeStruct) and self._items == other._items

    def __str__(self) -> str:
        defs = (
            f"{tp}:{key}" if i is None else f"{tp}:{key}:{i}"
            for i, tp, key in self.__seqiter(iter(self._items.items()))
        )
        return f"i{{{','.join(defs)}}}"

    @staticmethod
    def __seqiter(
        iiter: collections.abc.Iterator[tuple[int, tuple[RpcType, str]]],
    ) -> collections.abc.Iterator[tuple[int | None, RpcType, str]]:
        expected = 0
        for k, v in iiter:
            yield None if expected == k else k, v[0], v[1]
            expected = k + 1

    def __getitem__(self, key: int) -> tuple[RpcType, str]:
        return self._items[key]

    def __iter__(self) -> collections.abc.Iterator[int]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def validate(  # noqa: D102
        self, value: SHVType
    ) -> typing.TypeGuard[collections.abc.Mapping[int, SHVType]]:
        return (
            isinstance(value, collections.abc.Mapping)
            and all(k in self._items for k in value)
            and all(
                v[0].validate(typing.cast(SHVIMapType, value).get(k))
                for k, v in self._items.items()
            )
        )
