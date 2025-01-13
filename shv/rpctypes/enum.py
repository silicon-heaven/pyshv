"""SHV RPC type Enum."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVType
from .base import RpcType


class RpcTypeEnum(RpcType, collections.abc.Mapping[int, str]):
    """The Unsigned type representation."""

    def __init__(self, items: collections.abc.Mapping[int, str]) -> None:
        self._items = items
        if len(items) != len(set(items.values())):
            raise ValueError("Duplicates are not allowed in enum")

    def __str__(self) -> str:
        defs = (
            self._items[i] if seq else f"{self._items[i]}:{i}"
            for seq, i in self.__seqiter(iter(self._items))
        )
        return f"i[{','.join(defs)}]"

    @staticmethod
    def __seqiter(
        iiter: collections.abc.Iterator[int],
    ) -> collections.abc.Iterator[tuple[bool, int]]:
        expected = 0
        for i in iiter:
            yield expected == i, i
            expected = i + 1

    def __getitem__(self, key: int) -> str:
        return self._items[key]

    def __iter__(self) -> collections.abc.Iterator[int]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def validate(self, value: SHVType) -> typing.TypeGuard[int]:  # noqa: D102
        return isinstance(value, int) and value in self
