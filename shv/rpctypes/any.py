"""SHV RPC type matching any SHV value."""

from __future__ import annotations

import typing

from .. import SHVType
from .base import RpcType


class RpcTypeAny(RpcType):
    """The Any type representation."""

    __obj = None

    def __new__(cls, alias: str = "") -> RpcTypeAny:  # noqa: D102
        if alias:
            return super().__new__(cls)
        if cls.__obj is None:
            cls.__obj = object.__new__(cls)
        return cls.__obj

    def __init__(self, alias: str = "") -> None:
        self._alias = alias

    @property
    def alias(self) -> str:
        """The alias of this any type if provided."""
        return self._alias

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeAny) and self._alias == other._alias

    def __str__(self) -> str:
        return f"?{f'({self._alias})' if self._alias else ''}"

    @staticmethod
    def validate(value: SHVType) -> typing.TypeGuard[SHVType]:  # noqa: D102
        return True


rpctype_any = RpcTypeAny()
"""The singleton for :class:`RpcTypeAny`."""
