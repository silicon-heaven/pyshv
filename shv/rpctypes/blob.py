"""SHV RPC type blob."""

from __future__ import annotations

import typing

from .. import SHVType
from .base import RpcType


class RpcTypeBlob(RpcType):
    """The Blob type representation."""

    __obj: RpcTypeBlob | None = None

    def __new__(  # noqa: D102
        cls,
        minlen: int = 0,
        maxlen: int | None = None,
    ) -> RpcTypeBlob:
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
        if maxlen is not None and minlen > maxlen:
            raise ValueError("Minimum is greater than maximum")
        if minlen < 0 or (maxlen is not None and maxlen < 0):
            raise ValueError("Blob size can be only positive number")
        self._min = minlen
        self._max = maxlen

    @property
    def minlen(self) -> int:
        """Minimum length of the blob."""
        return self._min

    @property
    def maxlen(self) -> int | None:
        """Maximum length of the blob."""
        return self._max

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RpcTypeBlob)
            and self._min == other._min
            and self._max == other._max
        )

    def __str__(self) -> str:
        lim = ""
        if self._min != 0 or self._max is not None:
            if self._min == self._max:
                lim = f"({self._max})"
            else:
                lim = f"({self._min or ''},{self._max or ''})"
        return f"x{lim}"

    def is_valid(  # noqa: D102
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[bytes]:
        return self.validate(value, is_updatable) is None

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        if not isinstance(value, bytes):
            return "expected Blob"
        if self._min is not None and len(value) < self._min:
            return f"can't be shorter than {self._min} bytes"
        if self._max is not None and len(value) > self._max:
            return f"can't be longer than {self._max} bytes"
        return None


rpctype_blob = RpcTypeBlob()
"""Singleton for :class:`RpcTypeBlob` with no blob size limitation."""
