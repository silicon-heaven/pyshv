"""The SHV RPC type list."""

from __future__ import annotations

import typing

from .. import SHVListType, SHVType, is_shvlist
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

    def is_valid(  # noqa: D102
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[SHVListType]:
        return self.validate(value, is_updatable) is None

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        if not is_shvlist(value):
            return "expected List"
        vlen = len(value)
        if self._min == self._max:
            if vlen != self._max:
                return f"expected {self._max} number of List items"
        else:
            if self._min is not None and vlen < self._min:
                return f"expected at least {self._min} List items"
            if self._max is not None and vlen > self._max:
                return f"expected at most {self._max} List items"
        for i, val in enumerate(value):
            if (msg := self._tp.validate(val, is_updatable)) is not None:
                return f"invalid List item {i}: {msg}"
        return None

    def inflate(self, value: SHVType) -> SHVType:  # noqa: D102
        if not is_shvlist(value):
            raise ValueError("expected List")
        res = []
        for i, v in enumerate(value):
            try:
                res.append(self._tp.inflate(v))
            except ValueError as exc:
                raise ValueError(f"invalid List item {i}: {exc.args[0]}") from exc
        return res

    def deflate(self, value: SHVType) -> SHVType:  # noqa: D102
        if not is_shvlist(value):
            raise ValueError("expected List")
        res = []
        for i, v in enumerate(value):
            try:
                res.append(self._tp.deflate(v))
            except ValueError as exc:
                raise ValueError(f"invalid List item {i}: {exc.args[0]}") from exc
        return res


rpctype_list = RpcTypeList()
