"""SHV RPC type date and time."""

from __future__ import annotations

import datetime
import typing

from .. import SHVType
from .base import RpcType


class RpcTypeDateTime(RpcType):
    """The DateTime type representation."""

    __obj = None

    def __new__(cls) -> RpcTypeDateTime:  # noqa: D102
        if cls.__obj is None:
            cls.__obj = object.__new__(cls)
        return cls.__obj

    def __str__(self) -> str:
        return "t"

    @staticmethod
    def validate(value: SHVType) -> typing.TypeGuard[datetime.datetime]:  # noqa: D102
        return isinstance(value, datetime.datetime)


rpctype_datetime = RpcTypeDateTime()
"""The singleton for :class:`RpcTypeDateTime`."""
