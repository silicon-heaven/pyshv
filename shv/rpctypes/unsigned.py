"""The SHV RPC type Unsigned integer."""

from __future__ import annotations

import typing

from .. import SHVType
from ._tools import strnum as _strnum
from .base import RpcType


class RpcTypeUnsigned(RpcType):
    """The Unsigned type representation."""

    __obj: RpcTypeUnsigned | None = None

    def __new__(  # noqa: D102
        cls,
        minimum: int = 0,
        maximum: int | None = None,
        unit: str = "",
    ) -> RpcTypeUnsigned:
        if minimum == 0 and maximum is None and not unit:
            if cls.__obj is None:
                cls.__obj = super().__new__(cls)
            return cls.__obj
        return super().__new__(cls)

    def __init__(
        self,
        minimum: int = 0,
        maximum: int | None = None,
        unit: str = "",
    ) -> None:
        if maximum is not None and minimum > maximum:
            raise ValueError("Minimum is greater than maximum")
        if minimum < 0 or (maximum is not None and maximum < 0):
            raise ValueError("Unsigned limit can't be negative number")
        self._min = minimum
        self._max = maximum
        if any(c in "[]{}():,|" for c in unit):
            raise ValueError("Unit contains forbidden characters")
        self._unit = unit

    @property
    def minimum(self) -> int:
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
            isinstance(other, RpcTypeUnsigned)
            and self._min == other._min
            and self._max == other._max
            and self._unit == other._unit
        )

    def __str__(self) -> str:
        lim = ""
        if self._min != 0 or self._max is not None:
            if self._min == 0:
                lim = f"({_strnum(self._max)})"
            else:
                lim = f"({_strnum(self._min)},{_strnum(self._max)})"
        return f"u{lim}{self._unit}"

    def validate(self, value: SHVType) -> typing.TypeGuard[int]:  # noqa: D102
        return (
            isinstance(value, int)
            and value >= 0
            and (self._min is None or value >= self._min)
            and (self._max is None or value <= self._max)
        )


rpctype_unsigned = RpcTypeUnsigned()
