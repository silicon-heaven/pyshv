"""The SHV RPC type key-struct."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVMapType, SHVType
from .base import RpcType


class RpcTypeKeyStruct(RpcType, collections.abc.Mapping[str, RpcType]):
    """The KeyStruct type representation."""

    def __init__(self, items: collections.abc.Mapping[str, RpcType]) -> None:
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

    def validate(  # noqa: D102
        self, value: SHVType
    ) -> typing.TypeGuard[collections.abc.Mapping[str, SHVType]]:
        return (
            isinstance(value, collections.abc.Mapping)
            and all(k in self._items for k in value)
            and all(
                v.validate(typing.cast(SHVMapType, value).get(k))
                for k, v in self._items.items()
            )
        )
