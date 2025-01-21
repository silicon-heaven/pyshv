"""SHV RPC type decimal."""

from __future__ import annotations

import decimal
import typing

from .. import SHVType
from ._tools import strdec as _strdec
from ._tools import strnum as _strnum
from .base import RpcType


class RpcTypeDecimal(RpcType):
    """The Decimal type representation."""

    __obj: RpcTypeDecimal | None = None

    def __new__(  # noqa: D102
        cls,
        minimum: decimal.Decimal | None = None,
        maximum: decimal.Decimal | None = None,
        precision: int | None = None,
        unit: str = "",
    ) -> RpcTypeDecimal:
        if minimum is None and maximum is None and precision is None and not unit:
            if cls.__obj is None:
                cls.__obj = super().__new__(cls)
            return cls.__obj
        return super().__new__(cls)

    def __init__(
        self,
        minimum: decimal.Decimal | None = None,
        maximum: decimal.Decimal | None = None,
        precision: int | None = None,
        unit: str = "",
    ) -> None:
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("Minimum is greater than maximum")
        self._min = minimum
        self._max = maximum
        self._precs = precision
        if any(c in "[]{}():,|" for c in unit):
            raise ValueError("Unit contains forbidden characters")
        self._unit = unit

    @property
    def minimum(self) -> decimal.Decimal | None:
        """Minimum value allowed for this Decimal."""
        return self._min

    @property
    def maximum(self) -> decimal.Decimal | None:
        """Maximum value allowed for this Decimal."""
        return self._max

    @property
    def precision(self) -> int | None:
        """Precision of this decimal."""
        return self._precs

    @property
    def unit(self) -> str:
        """Unit to be appended to the number."""
        return self._unit

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RpcTypeDecimal)
            and self._min == other._min
            and self._max == other._max
            and self._precs == other._precs
            and self._unit == other._unit
        )

    def __str__(self) -> str:
        lim = ""
        if self._min is not None or self._max is not None or self._precs is not None:
            precs = "" if self._precs is None else f",{_strnum(self._precs)}"
            lim = f"({_strdec(self._min)},{_strdec(self._max)}{precs})"
        return f"d{lim}{self._unit}"

    def validate(self, value: SHVType) -> typing.TypeGuard[decimal.Decimal]:  # noqa: D102
        return (
            isinstance(value, decimal.Decimal)
            and (self._min is None or value >= self._min)
            and (self._max is None or value <= self._max)
            # TODO precision
        )


rpctype_decimal = RpcTypeDecimal()
"""The singleton for :class:`RpcTypeDecimal` with default parameters."""
