"""The SHV RPC type Bool."""

from __future__ import annotations

import typing

from .. import SHVType
from ..value import is_shvbool
from .base import RpcType


class RpcTypeBool(RpcType):
    """The Bool type representation."""

    __obj = None

    def __new__(cls) -> RpcTypeBool:  # noqa: D102
        if cls.__obj is None:
            cls.__obj = object.__new__(cls)
        return cls.__obj

    def __str__(self) -> str:
        return "b"

    @staticmethod
    def validate(value: SHVType) -> typing.TypeGuard[bool]:  # noqa: D102
        return is_shvbool(value)


rpctype_bool = RpcTypeBool()
"""The singleton for :class:`RpcTypeBool`."""
