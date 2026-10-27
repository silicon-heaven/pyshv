"""SHV RPC type date and time."""

from __future__ import annotations

import datetime
import typing

from .. import SHVType
from .base import RpcType


class RpcTypeDateTime(RpcType):
    """The DateTime type representation."""

    __obj = None

    def __new__(cls) -> RpcTypeDateTime:  # ruff: ignore[undocumented-public-method]
        if cls.__obj is None:
            cls.__obj = object.__new__(cls)
        return cls.__obj

    def __str__(self) -> str:
        return "t"

    def is_valid(  # ruff: ignore[undocumented-public-method]
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[datetime.datetime]:
        return self.validate(value, is_updatable) is None

    @staticmethod
    def validate(value: SHVType, is_updatable: bool = False) -> str | None:  # ruff: ignore[undocumented-public-method]
        if not isinstance(value, datetime.datetime):
            return "DateTime"
        return None


rpctype_datetime = RpcTypeDateTime()
"""The singleton for :class:`RpcTypeDateTime`."""
