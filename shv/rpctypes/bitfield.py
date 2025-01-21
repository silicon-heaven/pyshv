"""The SHV RPC type bitfield."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVType
from .base import RpcType
from .bool import RpcTypeBool
from .enum import RpcTypeEnum
from .unsigned import RpcTypeUnsigned


class RpcTypeBitfield(RpcType, collections.abc.Sequence[tuple[int, RpcType, str]]):
    """The Bitfield type representation."""

    def __init__(self, *items: tuple[int, RpcType, str]) -> None:
        self._items = sorted(items, key=lambda v: v[0])
        self._mask = 0
        end = -1
        for i in self._items:
            if i[0] < 0:
                raise ValueError("Bit index can't be negative number")
            if i[0] <= end:
                raise ValueError(f"Bit {i[0]} is used in multiple items")
            size = self.bitsize(i[1])
            if size is None:
                raise ValueError(f"Type '{i[1]}' can't be in Bitfield")
            end = i[0] + size - 1
            self._mask |= 2**size - 1 << i[0]

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeBitfield) and self._items == other._items

    def __str__(self) -> str:
        defs = (
            f"{tp}:{key}" if i is None else f"{tp}:{key}:{i}"
            for tp, key, i in self.__seqiter(self._items)
        )
        return f"u[{','.join(defs)}]"

    @classmethod
    def __seqiter(
        cls,
        iiter: collections.abc.Iterable[tuple[int, RpcType, str]],
    ) -> collections.abc.Iterator[tuple[RpcType, str, int | None]]:
        expected = 0
        for i, tp, key in iiter:
            yield tp, key, None if expected == i else i
            size = cls.bitsize(tp)
            assert isinstance(size, int)
            expected = i + size

    @typing.overload
    def __getitem__(self, i: int, /) -> tuple[int, RpcType, str]: ...

    @typing.overload
    def __getitem__(
        self, i: slice, /
    ) -> collections.abc.Sequence[tuple[int, RpcType, str]]: ...

    def __getitem__(
        self, i: int | slice
    ) -> tuple[int, RpcType, str] | collections.abc.Sequence[tuple[int, RpcType, str]]:
        return self._items[i]

    def __len__(self) -> int:
        return len(self._items)

    def validate(self, value: SHVType) -> typing.TypeGuard[int]:  # noqa: D102
        return (
            isinstance(value, int)
            and value ^ value & self._mask == 0
            and all(
                True
                if isinstance(tp, RpcTypeBool)
                else tp.validate(self.extract(value, s, tp))
                for s, tp, _ in self
            )
        )

    @staticmethod
    def bitsize(tp: RpcType) -> int | None:
        """Calculate bit size required for this type if supported.

        :param tp: The type bit size should be deduced for.
        :return: Number bits to be used in the bitfield or ``None`` if it can't
          be included.
        """
        match tp:
            case RpcTypeBool():
                return 1
            case RpcTypeUnsigned():
                if tp.maximum is not None and tp.maximum != tp.minimum:
                    return (tp.maximum - tp.minimum).bit_length()
            case RpcTypeEnum():
                return max(tp).bit_length()
        return None

    @classmethod
    def extract(cls, value: int, start: int, tp: RpcType) -> int:
        """Extract integer based on the provided type and start.

        The handling is based on the type:
        * ``b``: ``1`` is returned for true and ``0`` for false.
        * ``u(MAX)``: number is returned as extracter.
        * ``u(MIN,MAX)``: number is returned with added ``MIN``.
        * ``i[]``: number is returned as extracted.
        """
        size = cls.bitsize(tp)
        if size is None:
            raise ValueError(f"Type '{tp} can't be in Bitfield")
        result: int = value >> start & (2**size - 1)
        if isinstance(tp, RpcTypeUnsigned) and tp.minimum > 0:
            result += tp.minimum
        return result

    @classmethod
    def deposit(cls, value: int, start: int, tp: RpcType, update: int = 0) -> int:
        """Insert integer based on the provided type and start.

        The handling is based on the type:
        * ``b``: odd numbers are inserted as true and even numbers as false.
        * ``u(MAX)``: number is inserted as is.
        * ``u(MIN,MAX)``: number is inserted minus the ``MIN``.
        * ``i[]``: number is inserted as is.
        """
        if isinstance(value, bool):
            value = 1 if value else 0
        elif not tp.validate(value):
            raise ValueError(f"Value '{value}' is invalid for type '{tp}'")
        elif isinstance(tp, RpcTypeUnsigned) and tp.minimum > 0:
            value -= tp.minimum
        size = cls.bitsize(tp)
        if size is None:
            raise ValueError(f"Type '{tp} can't be in Bitfield")
        mask: int = 2**size - 1
        return (value & mask) << start | update ^ mask << start
