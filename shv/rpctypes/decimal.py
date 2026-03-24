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
        minimum: decimal.Decimal | str | None = None,
        maximum: decimal.Decimal | str | None = None,
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
        minimum: decimal.Decimal | str | None = None,
        maximum: decimal.Decimal | str | None = None,
        precision: int | None = None,
        unit: str = "",
    ) -> None:
        if isinstance(minimum, str):
            minimum = decimal.Decimal(minimum)
        if isinstance(maximum, str):
            maximum = decimal.Decimal(maximum)
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

    def is_valid(  # noqa: D102
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[decimal.Decimal]:
        return self.validate(value, is_updatable) is None

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        if not isinstance(value, decimal.Decimal):
            return "expected Decimal"
        if not value.is_finite():
            return "only finite Decimal numbers are allowed"
        if self._min is not None and value < self._min:
            return f"less than minimum value {self._min}"
        if self._max is not None and value > self._max:
            return f"more than maximum value {self._max}"
        if self._precs is not None:
            exp = value.normalize().as_tuple().exponent
            assert isinstance(exp, int)  # It is finite so always True
            if self._precs * -1 > exp:
                return f"maximum precision is {self._precs}"
        return None


rpctype_decimal = RpcTypeDecimal()
"""The singleton for :class:`RpcTypeDecimal` with default parameters."""
