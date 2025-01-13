"""The SHV RPC type Int."""

from __future__ import annotations

import typing

from .. import SHVType
from ._tools import strnum as _strnum
from .base import RpcType


class RpcTypeInteger(RpcType):
    """The Integer type representation."""

    __obj: RpcTypeInteger | None = None

    def __new__(  # noqa: D102
        cls,
        minimum: int | None = None,
        maximum: int | None = None,
        unit: str = "",
    ) -> RpcTypeInteger:
        if minimum is None and maximum is None and not unit:
            if cls.__obj is None:
                cls.__obj = super().__new__(cls)
            return cls.__obj
        return super().__new__(cls)

    def __init__(
        self,
        minimum: int | None = None,
        maximum: int | None = None,
        unit: str = "",
    ) -> None:
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("Minimum is greater than maximum")
        self._min = minimum
        self._max = maximum
        if any(c in "[]{}():,|" for c in unit):
            raise ValueError("Unit contains forbidden characters")
        self._unit = unit

    @property
    def minimum(self) -> int | None:
        """Minimum value allowed for this Int."""
        return self._min

    @property
    def maximum(self) -> int | None:
        """Maximum value allowed for this Int."""
        return self._max

    @property
    def unit(self) -> str:
        """Unit to be appended to the number."""
        return self._unit

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RpcTypeInteger)
            and self._min == other._min
            and self._max == other._max
            and self._unit == other._unit
        )

    def __str__(self) -> str:
        lim = ""
        if self._min is not None or self._max is not None:
            lim = f"({_strnum(self._min)},{_strnum(self._max)})"
        return f"i{lim}{self._unit}"

    def validate(self, value: SHVType) -> typing.TypeGuard[int]:  # noqa: D102
        return (
            isinstance(value, int)
            and (self._min is None or value >= self._min)
            and (self._max is None or value <= self._max)
        )


rpctype_integer = RpcTypeInteger()
"""Singleton for :class:`RpcTypeInteger` with default parameters."""
