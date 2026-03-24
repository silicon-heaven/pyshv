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
    def is_valid(  # noqa: D102
        value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[bool]:
        return is_shvbool(value)

    @classmethod
    def validate(cls, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        return "expected Bool" if not cls.is_valid(value) else None


rpctype_bool = RpcTypeBool()
"""The singleton for :class:`RpcTypeBool`."""
