"""The SHV RPC type Null."""

from __future__ import annotations

import typing

from .. import SHVType
from ..value import is_shvnull
from .base import RpcType


class RpcTypeNull(RpcType):
    """The Null type representation."""

    __obj = None

    def __new__(cls) -> RpcTypeNull:  # ruff: ignore[undocumented-public-method]
        if cls.__obj is None:
            cls.__obj = object.__new__(cls)
        return cls.__obj

    def __str__(self) -> str:
        return "n"

    @staticmethod
    def is_valid(  # ruff: ignore[undocumented-public-method]
        value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[None]:
        return is_shvnull(value)

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # ruff: ignore[undocumented-public-method]
        if not self.is_valid(value):
            return "Null"
        return None


rpctype_null = RpcTypeNull()
"""The singleton for :class:`RpcTypeNull`."""
