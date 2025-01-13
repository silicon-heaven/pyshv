"""SHV RPC type Double."""

from __future__ import annotations

import typing

from .. import SHVType
from .base import RpcType


class RpcTypeDouble(RpcType):
    """The Double type representation."""

    __obj: RpcTypeDouble | None = None

    def __new__(cls, unit: str = "") -> RpcTypeDouble:  # noqa: D102
        if not unit:
            if cls.__obj is None:
                cls.__obj = super().__new__(cls)
            return cls.__obj
        return super().__new__(cls)

    def __init__(self, unit: str = "") -> None:
        if any(c in "[]{}():,|" for c in unit):
            raise ValueError("Unit contains forbidden characters")
        self._unit = unit

    @property
    def unit(self) -> str:
        """Unit to be appended to the number."""
        return self._unit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeDouble) and self._unit == other._unit

    def __str__(self) -> str:
        return f"f{self._unit}"

    @staticmethod
    def validate(value: SHVType) -> typing.TypeGuard[float]:  # noqa: D102
        return isinstance(value, float)


rpctype_double = RpcTypeDouble()
"""The singleton for :class:`RpcTypeDouble`."""
