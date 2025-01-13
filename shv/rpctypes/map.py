"""The SHV RPC type map."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVType
from .any import rpctype_any
from .base import RpcType


class RpcTypeMap(RpcType):
    """The Map type representation."""

    __obj: RpcTypeMap | None = None

    def __new__(cls, tp: RpcType = rpctype_any) -> RpcTypeMap:  # noqa: D102
        if tp is rpctype_any:
            if cls.__obj is None:
                cls.__obj = super().__new__(cls)
            return cls.__obj
        return super().__new__(cls)

    def __init__(self, tp: RpcType = rpctype_any) -> None:
        self._tp = tp

    @property
    def type(self) -> RpcType:
        """Content type allowed to be used in the Map as values."""
        return self._tp

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeMap) and self._tp == other._tp

    def __str__(self) -> str:
        return f"{{{self._tp}}}"

    def validate(  # noqa: D102
        self, value: SHVType
    ) -> typing.TypeGuard[collections.abc.Mapping[str, SHVType]]:
        return isinstance(value, collections.abc.Mapping) and all(
            isinstance(k, str) and self._tp.validate(v) for k, v in value.items()
        )


rpctype_map = RpcTypeMap()
"""The singleton for :class:`RpcTypeMap`."""
