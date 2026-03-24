"""The SHV RPC type struct."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVIMapType, SHVMapType, SHVType, is_shvimap, is_shvmap
from .base import RpcType


class RpcTypeStructItem(typing.NamedTuple):
    """Single Item definition for the :class:`RpcTypeStruct`."""

    tp: RpcType
    """RPC type for the item."""
    key: str
    """String alias used to identify this item."""


class RpcTypeStruct(RpcType, collections.abc.Mapping[int, RpcTypeStructItem]):
    """The Struct type representation."""

    def __init__(
        self,
        items: collections.abc.Mapping[int, RpcTypeStructItem | tuple[RpcType, str]],
    ) -> None:
        if len(items) == 0:
            raise ValueError("Struct requires at least one item")
        if len(items) != len(set(v[1] for v in items.values())):
            raise ValueError("Duplicate keys are not allowed")
        self._items = {
            k: v if isinstance(v, RpcTypeStructItem) else RpcTypeStructItem(*v)
            for k, v in items.items()
        }
        self._index = {v.key: k for k, v in self._items.items()}

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
        iiter: collections.abc.Iterator[tuple[int, RpcTypeStructItem]],
    ) -> collections.abc.Iterator[tuple[int | None, RpcType, str]]:
        expected = 0
        for k, v in iiter:
            yield None if expected == k else k, v[0], v[1]
            expected = k + 1

    def __getitem__(self, key: int) -> RpcTypeStructItem:
        return self._items[key]

    def __iter__(self) -> collections.abc.Iterator[int]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def is_valid(  # noqa: D102
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[SHVIMapType]:
        return self.validate(value, is_updatable) is None

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        if not is_shvimap(value):
            return "expected Struct"
        if invalid := set(value) - set(self._items):
            return f"undefined Struct key: {', '.join(str(v) for v in invalid)}"
        for i, item in self.items():
            val = value.get(i, None)
            if val is not None or not is_updatable:  # Allow None on update
                if (msg := item[0].validate(val, is_updatable)) is not None:
                    return f"invalid Struct item {i}: {msg}"
        return None

    def inflate(self, value: SHVType) -> SHVMapType:  # noqa: D102
        if not is_shvimap(value):
            raise ValueError("expected Struct")
        if unknown := set(value.keys()) - set(self._items):
            raise ValueError(
                f"undefined Struct key: {', '.join(str(v) for v in unknown)}"
            )
        res = {}
        for i, item in self._items.items():
            try:
                v = item[0].inflate(value.get(i, None))
            except ValueError as exc:
                raise ValueError(f"invalid Struct item {i}: {exc.args[0]}") from exc
            if v is not None:
                res[item[1]] = v
        return res

    def deflate(self, value: SHVType) -> SHVIMapType:  # noqa: D102
        if not is_shvmap(value):
            raise ValueError("expected Map(Struct)")
        if unknown := set(value.keys()) - set(self._index):
            raise ValueError(f"undefined Struct key: {', '.join(unknown)}")
        res = {}
        for i, item in self._items.items():
            try:
                v = item[0].deflate(value.get(item[1], None))
            except ValueError as exc:
                raise ValueError(f"invalid Struct item {i}: {exc.args[0]}") from exc
            if v is not None:
                res[i] = v
        return res
