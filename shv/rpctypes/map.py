"""The SHV RPC type map."""

from __future__ import annotations

import typing

from .. import SHVMapType, SHVType, is_shvmap
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

    def is_valid(  # noqa: D102
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[SHVMapType]:
        return self.validate(value, is_updatable) is None

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        if not is_shvmap(value):
            return "expected Map"
        for k, val in value.items():
            if (msg := self._tp.validate(val, is_updatable)) is not None:
                return f"invalid Map item {k}: {msg}"
        return None

    def inflate(self, value: SHVType) -> SHVMapType:  # noqa: D102
        if not is_shvmap(value):
            raise ValueError("expected Map")
        res = {}
        for k, v in value.items():
            try:
                res[k] = self._tp.inflate(v)
            except ValueError as exc:
                raise ValueError(f"invalid Map item {k}: {exc.args[0]}") from exc
        return res

    def deflate(self, value: SHVType) -> SHVMapType:  # noqa: D102
        if not is_shvmap(value):
            raise ValueError("expected Map")
        res = {}
        for k, v in value.items():
            try:
                res[k] = self._tp.deflate(v)
            except ValueError as exc:
                raise ValueError(f"invalid Map item {k}: {exc.args[0]}") from exc
        return res


rpctype_map = RpcTypeMap()
"""The singleton for :class:`RpcTypeMap`."""
