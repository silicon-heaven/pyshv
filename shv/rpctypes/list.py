"""The SHV RPC type list."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVType
from .any import rpctype_any
from .base import RpcType


class RpcTypeList(RpcType):
    """The List type representation."""

    __obj: RpcTypeList | None = None

    def __new__(  # noqa: D102
        cls, tp: RpcType = rpctype_any, minlen: int = 0, maxlen: int | None = None
    ) -> RpcTypeList:
        if tp is rpctype_any and minlen == 0 and maxlen is None:
            if cls.__obj is None:
                cls.__obj = super().__new__(cls)
            return cls.__obj
        return super().__new__(cls)

    def __init__(
        self, tp: RpcType = rpctype_any, minlen: int = 0, maxlen: int | None = None
    ) -> None:
        if maxlen is not None and minlen > maxlen:
            raise ValueError("Minimum is greater than maximum")
        if minlen < 0 or (maxlen is not None and maxlen < 0):
            raise ValueError("List size can be only positive number")
        self._tp = tp
        self._min = minlen
        self._max = maxlen

    @property
    def type(self) -> RpcType:
        """Content type allowed to be used in the list."""
        return self._tp

    @property
    def minlen(self) -> int:
        """Minimum number of items in the list."""
        return self._min

    @property
    def maxlen(self) -> int | None:
        """Maximum number of items in the list."""
        return self._max

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RpcTypeList)
            and self._tp == other._tp
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
        return f"[{self._tp}]{lim}"

    def validate(self, value: SHVType) -> typing.TypeGuard[collections.abc.Sequence]:  # noqa: D102
        return isinstance(value, collections.abc.Sequence) and all(
            self._tp.validate(v) for v in value
        )


rpctype_list = RpcTypeList()
