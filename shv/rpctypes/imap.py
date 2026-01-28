"""The SHV RPC type imap."""

from __future__ import annotations

import typing

from .. import SHVIMapType, SHVType, is_shvimap
from .any import rpctype_any
from .base import RpcType


class RpcTypeIMap(RpcType):
    """The IMap type representation."""

    __obj: RpcTypeIMap | None = None

    def __new__(cls, tp: RpcType = rpctype_any) -> RpcTypeIMap:  # noqa: D102
        if tp is rpctype_any:
            if cls.__obj is None:
                cls.__obj = super().__new__(cls)
            return cls.__obj
        return super().__new__(cls)

    def __init__(self, tp: RpcType = rpctype_any) -> None:
        self._tp = tp

    @property
    def type(self) -> RpcType:
        """Content type allowed to be used in the IMap as values."""
        return self._tp

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeIMap) and self._tp == other._tp

    def __str__(self) -> str:
        return f"i{{{self._tp}}}"

    def is_valid(self, value: SHVType) -> typing.TypeGuard[SHVIMapType]:  # noqa: D102
        return self.validate(value) is None

    def validate(self, value: SHVType) -> str | None:  # noqa: D102
        if not is_shvimap(value):
            return "expected IMap"
        for i, val in value.items():
            if (msg := self._tp.validate(val)) is not None:
                return f"invalid IMap item {i}: {msg}"
        return None

    def inflate(self, value: SHVType) -> SHVIMapType:  # noqa: D102
        if not is_shvimap(value):
            raise ValueError("expected IMap")
        res = {}
        for i, v in value.items():
            try:
                res[i] = self._tp.inflate(v)
            except ValueError as exc:
                raise ValueError(f"invalid IMap item {i}: {exc.args[0]}") from exc
        return res

    def deflate(self, value: SHVType) -> SHVIMapType:  # noqa: D102
        if not is_shvimap(value):
            raise ValueError("expected IMap")
        res = {}
        for i, v in value.items():
            try:
                res[i] = self._tp.deflate(v)
            except ValueError as exc:
                raise ValueError(f"invalid IMap item {i}: {exc.args[0]}") from exc
        return res


rpctype_imap = RpcTypeIMap()
"""The singleton for :class:`RpcTypeIMap`."""
