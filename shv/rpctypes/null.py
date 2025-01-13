"""The SHV RPC type Null."""

from __future__ import annotations

import typing

from .. import SHVType
from ..value import is_shvnull
from .base import RpcType


class RpcTypeNull(RpcType):
    """The Null type representation."""

    __obj = None

    def __new__(cls) -> RpcTypeNull:  # noqa: D102
        if cls.__obj is None:
            cls.__obj = object.__new__(cls)
        return cls.__obj

    def __str__(self) -> str:
        return "n"

    @staticmethod
    def validate(value: SHVType) -> typing.TypeGuard[None]:  # noqa: D102
        return is_shvnull(value)


rpctype_null = RpcTypeNull()
"""The singleton for :class:`RpcTypeNull`."""
