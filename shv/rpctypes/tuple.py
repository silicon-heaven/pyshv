"""The SHV RPC type tuple."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVListType, SHVMapType, SHVType, is_shvlist, is_shvmap
from .base import RpcType


class RpcTypeTupleItem(typing.NamedTuple):
    """Single Item definition for the :class:`RpcTypeTuple`."""

    tp: RpcType
    """RPC type for the item."""
    key: str
    """String alias used to identify this item."""


class RpcTypeTuple(RpcType, collections.abc.Sequence[RpcTypeTupleItem]):
    """The Tuple type representation."""

    def __init__(self, *args: RpcTypeTupleItem | tuple[RpcType, str]) -> None:
        if len(args) < 1:
            raise ValueError("Tuple requires at least one item")
        self._items = [
            item if isinstance(item, RpcTypeTupleItem) else RpcTypeTupleItem(*item)
            for item in args
        ]

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeTuple) and self._items == other._items

    def __str__(self) -> str:
        return f"[{','.join(f'{tp}:{key}' for tp, key in self._items)}]"

    @typing.overload
    def __getitem__(self, i: int, /) -> RpcTypeTupleItem: ...

    @typing.overload
    def __getitem__(
        self, i: slice, /
    ) -> collections.abc.Sequence[RpcTypeTupleItem]: ...

    def __getitem__(
        self, i: int | slice
    ) -> RpcTypeTupleItem | collections.abc.Sequence[RpcTypeTupleItem]:
        return self._items[i]

    def __len__(self) -> int:
        return len(self._items)

    def minlen(self) -> int:
        """Minimal length of the valid List matching the Tuple."""
        res = len(self._items)
        while res > 0 and self._items[res - 1][0].is_valid(None):
            res -= 1
        return res

    def is_valid(  # noqa: D102
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[SHVListType]:
        return self.validate(value, is_updatable) is None

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        if not is_shvlist(value):
            return "expected Tuple"
        vlen = len(value)
        if vlen > len(self._items):
            return "too many Tuple items"
        for i, item in enumerate(self._items):
            val = value[i] if i < vlen else None
            if val is not None or not is_updatable:  # Allow None on update
                if (msg := item.tp.validate(val, is_updatable)) is not None:
                    return f"invalid for Tuple item {item.key}: {msg}"
        return None

    def inflate(self, value: SHVType) -> SHVMapType:  # noqa: D102
        if not is_shvlist(value):
            raise ValueError("expected Tuple")
        vlen = len(value)
        res = {}
        for i, item in enumerate(self._items):
            v = value[i] if i < vlen else None
            try:
                res[item.key] = item.tp.inflate(v)
            except ValueError as exc:
                raise ValueError(f"invalid Tuple item {i}: {exc.args[0]}") from exc
        return res

    def deflate(self, value: SHVType) -> SHVListType:  # noqa: D102
        if not is_shvmap(value):
            raise ValueError("expected Map(Tuple)")
        keys = set(value.keys())
        if unknown := keys - {v.key for v in self}:
            raise ValueError(f"undefined Tuple key: {', '.join(unknown)}")
        minlen = self.minlen()
        res = []
        for i, item in enumerate(self._items):
            v = value.get(item.key, None)
            try:
                res.append(item.tp.deflate(v))
            except ValueError as exc:
                raise ValueError(f"invalid Tuple item {i}: {exc.args[0]}") from exc
            keys.remove(item.key)
            if not keys and i >= minlen:
                break
        while res[-1] is None:
            del res[-1]
        return res
