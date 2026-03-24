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

    def is_valid(  # noqa: D102
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[int]:
        return super().is_valid(value, is_updatable)

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        if not isinstance(value, int):
            return "expected Integer(Enum)"
        if value not in self:
            return "undefined value in Enum"
        return None

    def inflate(self, value: SHVType) -> SHVType:  # noqa: D102
        if msg := self.validate(value):
            raise ValueError(msg)
        assert isinstance(value, int)
        return self[value]

    def deflate(self, value: SHVType) -> SHVType:  # noqa: D102
        if not isinstance(value, str):
            raise ValueError("expected String(Enum)")
        try:
            return next(i for i, name in self.items() if name == value)
        except StopIteration as exc:
            raise ValueError("undefined value in Enum") from exc
