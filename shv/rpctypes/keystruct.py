"""The SHV RPC type key-struct."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVMapType, SHVType, is_shvmap
from .base import RpcType


class RpcTypeKeyStruct(RpcType, collections.abc.Mapping[str, RpcType]):
    """The KeyStruct type representation."""

    def __init__(self, items: collections.abc.Mapping[str, RpcType]) -> None:
        if len(items) == 0:
            raise ValueError("KeyStruct requires at least one item")
        self._items = items

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeKeyStruct) and self._items == other._items

    def __str__(self) -> str:
        return f"{{{','.join(f'{tp}:{key}' for key, tp in self._items.items())}}}"

    def __getitem__(self, key: str) -> RpcType:
        return self._items[key]

    def __iter__(self) -> collections.abc.Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def is_valid(  # noqa: D102
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[SHVMapType]:
        return self.validate(value, is_updatable) is None

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        if not is_shvmap(value):
            return "expected KeyStruct"
        if invalid := set(value) - set(self._items):
            return f"undefined KeyStruct key: {', '.join(str(v) for v in invalid)}"
        for k, item in self.items():
            val = value.get(k, None)
            if val is not None or not is_updatable:  # Allow None on update
                if (msg := item.validate(val, is_updatable)) is not None:
                    return f"invalid KeyStruct item {k}: {msg}"
        return None

    def inflate(self, value: SHVType) -> SHVMapType:  # noqa: D102
        if not is_shvmap(value):
            raise ValueError("expected KeyStruct")
        if unknown := set(value.keys()) - set(self._items):
            raise ValueError(f"undefined KeyStruct key: {', '.join(unknown)}")
        res = {}
        for k, item in self._items.items():
            try:
                v = item.inflate(value.get(k, None))
            except ValueError as exc:
                raise ValueError(f"invalid KeyStruct item {k}: {exc.args[0]}") from exc
            if v is not None:
                res[k] = v
        return res

    def deflate(self, value: SHVType) -> SHVMapType:  # noqa: D102
        if not is_shvmap(value):
            raise ValueError("expected KeyStruct")
        if unknown := set(value.keys()) - set(self._items):
            raise ValueError(f"undefined KeyStruct key: {', '.join(unknown)}")
        res = {}
        for k, item in self._items.items():
            try:
                v = item.deflate(value.get(k, None))
            except ValueError as exc:
                raise ValueError(f"invalid KeyStruct item {k}: {exc.args[0]}") from exc
            if v is not None:
                res[k] = v
        return res
