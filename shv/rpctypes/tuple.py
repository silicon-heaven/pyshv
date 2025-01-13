"""The SHV RPC type tuple."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVType
from .base import RpcType


class RpcTypeTuple(RpcType, collections.abc.Sequence[tuple[RpcType, str]]):
    """The Tuple type representation."""

    def __init__(self, *args: tuple[RpcType, str]) -> None:
        self._items = args

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeTuple) and self._items == other._items

    def __str__(self) -> str:
        return f"[{','.join(f'{tp}:{key}' for tp, key in self._items)}]"

    @typing.overload
    def __getitem__(self, i: int, /) -> tuple[RpcType, str]: ...

    @typing.overload
    def __getitem__(
        self, i: slice, /
    ) -> collections.abc.Sequence[tuple[RpcType, str]]: ...

    def __getitem__(
        self, i: int | slice
    ) -> tuple[RpcType, str] | collections.abc.Sequence[tuple[RpcType, str]]:
        return self._items[i]

    def __len__(self) -> int:
        return len(self._items)

    def validate(self, value: SHVType) -> typing.TypeGuard[collections.abc.Sequence]:  # noqa: D102
        if not isinstance(value, collections.abc.Sequence):
            return False
        if len(value) > len(self._items):
            return False
        for i, item in enumerate(self._items):
            if not item[0].validate(value[i] if len(value) > i else None):
                return False
        return True
