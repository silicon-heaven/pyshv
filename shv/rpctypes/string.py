"""SHV RPC type String."""

from __future__ import annotations

import typing

from .. import SHVType
from .base import RpcType


class RpcTypeString(RpcType):
    """The String type representation."""

    __obj: RpcTypeString | None = None

    def __new__(  # noqa: D102
        cls,
        minlen: int = 0,
        maxlen: int | None = None,
    ) -> RpcTypeString:
        if minlen == 0 and maxlen is None:
            if cls.__obj is None:
                cls.__obj = super().__new__(cls)
            return cls.__obj
        return super().__new__(cls)

    def __init__(
        self,
        minlen: int = 0,
        maxlen: int | None = None,
    ) -> None:
        self._min = minlen
        self._max = maxlen

    @property
    def minlen(self) -> int:
        """Minimum length of the string."""
        return self._min

    @property
    def maxlen(self) -> int | None:
        """Maximum length of the string."""
        return self._max

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RpcTypeString)
            and self._min == other._min
            and self._max == other._max
        )

    def __str__(self) -> str:
        lim = ""
        if self._min != 0 or self._max is not None:
            if self._min == self._max:
                lim = f"({self._max})"
            else:
                lim = f"({self._min if self._min else ''},{self._max})"
        return f"s{lim}"

    def validate(self, value: SHVType) -> typing.TypeGuard[str]:  # noqa: D102
        return (
            isinstance(value, str)
            and (self._min is None or len(value) >= self._min)
            and (self._max is None or len(value) <= self._max)
        )


rpctype_string = RpcTypeString()
"""Singleton for :class:`RpcTypeString` with no string size limitation."""
