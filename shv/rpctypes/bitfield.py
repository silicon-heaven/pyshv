"""The SHV RPC type bitfield."""

from __future__ import annotations

import collections.abc
import typing

from .. import SHVBoolType, SHVMapType, SHVType, SHVUInt, is_shvmap
from .base import RpcType
from .bool import RpcTypeBool, rpctype_bool
from .enum import RpcTypeEnum
from .unsigned import RpcTypeUnsigned

SHVTypeBitfieldCompatible: typing.TypeAlias = SHVBoolType | SHVUInt | int
RpcTypeBitfieldCompatible: typing.TypeAlias = (
    RpcTypeBool | RpcTypeEnum | RpcTypeUnsigned
)


class RpcTypeBitfieldItem(typing.NamedTuple):
    """Single Item definition for the :class:`RpcTypeBitfield`."""

    startbit: int
    """The bit in the bitfield this item starts on."""
    tp: RpcTypeBitfieldCompatible
    """RPC type for the item."""
    key: str
    """String alias used to identify this item."""


class RpcTypeBitfield(RpcType, collections.abc.Sequence[RpcTypeBitfieldItem]):
    """The Bitfield type representation."""

    def __init__(
        self, *items: RpcTypeBitfieldItem | tuple[int, RpcTypeBitfieldCompatible, str]
    ) -> None:
        self._items = sorted(
            (
                item
                if isinstance(item, RpcTypeBitfieldItem)
                else RpcTypeBitfieldItem(*item)
                for item in items
            ),
            key=lambda v: v.startbit,
        )
        self._mask = 0
        end = -1
        for item in self._items:
            if item.startbit < 0:
                raise ValueError("Bit index can't be negative number")
            if item.startbit <= end:
                raise ValueError(f"Bit {item.startbit} is used in multiple items")
            size = self.bitsize(item.tp)
            end = item.startbit + size - 1
            self._mask |= 2**size - 1 << item.startbit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RpcTypeBitfield) and self._items == other._items

    def __str__(self) -> str:
        defs = (
            f"{tp}:{key}" if startbit is None else f"{tp}:{key}:{startbit}"
            for tp, key, startbit in self.__seqiter(self._items)
        )
        return f"u[{','.join(defs)}]"

    @classmethod
    def __seqiter(
        cls, iiter: collections.abc.Iterable[RpcTypeBitfieldItem]
    ) -> collections.abc.Iterator[tuple[RpcTypeBitfieldCompatible, str, int | None]]:
        expected = 0
        for item in iiter:
            yield (
                item.tp,
                item.key,
                None if expected == item.startbit else item.startbit,
            )
            size = cls.bitsize(item.tp)
            assert isinstance(size, int)
            expected = item.startbit + size

    @typing.overload
    def __getitem__(self, i: int, /) -> RpcTypeBitfieldItem: ...

    @typing.overload
    def __getitem__(
        self, i: slice, /
    ) -> collections.abc.Sequence[RpcTypeBitfieldItem]: ...

    def __getitem__(
        self, i: int | slice
    ) -> RpcTypeBitfieldItem | collections.abc.Sequence[RpcTypeBitfieldItem]:
        return self._items[i]

    def __len__(self) -> int:
        return len(self._items)

    def is_valid(  # noqa: D102
        self, value: SHVType, is_updatable: bool = False
    ) -> typing.TypeGuard[int]:
        return self.validate(value, is_updatable) is None

    def validate(self, value: SHVType, is_updatable: bool = False) -> str | None:  # noqa: D102
        if not isinstance(value, int):
            return "expected Bitfield"
        if (v := self._mask & value ^ value) != 0:
            return f"unused bits in Bitfield must be zero: {bin(v)}"
        for item in self:
            if not isinstance(item.tp, RpcTypeBool):  # Bit is always valid for Bool
                try:
                    self.extract(value, item.startbit, item.tp)
                except ValueError as exc:
                    return f"invalid Bitfield item {item.key}: {exc.args[0]}"
        return None

    def inflate(self, value: SHVType) -> SHVMapType:  # noqa: D102
        if not isinstance(value, int):
            raise ValueError("expected Bitfield")
        if (vi := self._mask & value ^ value) != 0:
            raise ValueError(f"unused bits in Bitfield must be zero: {bin(vi)}")
        res = {}
        for i, item in enumerate(self):
            try:
                v = item.tp.inflate(self.extract(value, item.startbit, item.tp))
            except ValueError as exc:
                raise ValueError(f"invalid Bitfield item {i}: {exc.args[0]}") from exc
            res[item.key] = v
        return res

    def deflate(self, value: SHVType) -> int:  # noqa: D102
        if not is_shvmap(value):
            raise ValueError("expected Map(Bitfield)")
        if unknown := set(value.keys()) - {item[2] for item in self._items}:
            raise ValueError(f"undefined Bitfield key: {', '.join(unknown)}")
        res = 0
        for i, item in enumerate(self):
            try:
                v = item.tp.deflate(value[item.key])
            except KeyError as exc:
                raise ValueError(f"missing Bitfield item {i}") from exc
            except ValueError as exc:
                raise ValueError(f"invalid Bitfield item {i}: {exc.args[0]}") from exc
            res = self.deposit(
                typing.cast(SHVTypeBitfieldCompatible, v), item.startbit, item.tp, res
            )
        return res

    @staticmethod
    def is_supported(tp: RpcType) -> typing.TypeGuard[RpcTypeBitfieldCompatible]:
        """Check if given type is compatible with bitfield."""
        return (
            tp is rpctype_bool
            or (isinstance(tp, RpcTypeEnum) and all(v >= 0 for v in tp))
            or (isinstance(tp, RpcTypeUnsigned) and tp.minimum >= 0)
        )

    @staticmethod
    def bitsize(tp: RpcTypeBitfieldCompatible) -> int:
        """Calculate bit size required for this type if supported.

        :param tp: The type bit size should be deduced for.
        :return: Number bits to be used in the bitfield.
        :raise ValueError: in case ``tp`` is not of compatible type.
        """
        match tp:
            case RpcTypeBool():
                return 1
            case RpcTypeUnsigned():
                if tp.maximum is not None and tp.maximum != tp.minimum:
                    return (tp.maximum - tp.minimum).bit_length()
            case RpcTypeEnum():
                return max(tp).bit_length()
        raise ValueError(f"Type '{tp}' not supported in Bitfield")

    @classmethod
    @typing.overload
    def extract(cls, value: int, start: int, tp: RpcTypeBool) -> bool: ...

    @classmethod
    @typing.overload
    def extract(cls, value: int, start: int, tp: RpcTypeEnum) -> int: ...

    @classmethod
    @typing.overload
    def extract(cls, value: int, start: int, tp: RpcTypeUnsigned) -> SHVUInt: ...

    @classmethod
    def extract(
        cls, value: int, start: int, tp: RpcTypeBitfieldCompatible
    ) -> SHVTypeBitfieldCompatible:
        """Extract integer based on the provided type and start.

        The handling is based on the type:
        * ``b``: ``1`` is returned for true and ``0`` for false.
        * ``u(MAX)``: number is returned as extracted.
        * ``u(MIN,MAX)``: number is returned with added ``MIN``.
        * ``i[...]``: number is returned as extracted.

        :param value: The Bitfield value.
        :param start: Bit offset to the type.
        :param tp: Type of the value to be extracted.
        :raise ValueError: In case extracted value is invalid for the given
          type or if type is not supported in Bitfield at all.
        """
        bitsize = cls.bitsize(tp)
        match tp:
            case RpcTypeBool():
                return True if value & 1 << start else False
            case RpcTypeUnsigned():
                ures = SHVUInt((value >> start & (2**bitsize - 1)) + tp.minimum)
                if msg := tp.validate(ures):
                    raise ValueError(msg)
                return ures
            case RpcTypeEnum():
                eres = int(value >> start & (2**bitsize - 1))
                if msg := tp.validate(eres):
                    raise ValueError(msg)
                return eres
            case _:  # pragma: no cover
                raise NotImplementedError

    @classmethod
    @typing.overload
    def deposit(cls, value: bool, start: int, tp: RpcTypeBool, update: int) -> int: ...

    @classmethod
    @typing.overload
    def deposit(cls, value: int, start: int, tp: RpcTypeEnum, update: int) -> int: ...

    @classmethod
    @typing.overload
    def deposit(
        cls, value: SHVUInt, start: int, tp: RpcTypeUnsigned, update: int
    ) -> int: ...

    @classmethod
    @typing.overload
    def deposit(
        cls,
        value: SHVTypeBitfieldCompatible,
        start: int,
        tp: RpcTypeBitfieldCompatible,
        update: int,
    ) -> int: ...

    @classmethod
    def deposit(
        cls,
        value: SHVTypeBitfieldCompatible,
        start: int,
        tp: RpcTypeBitfieldCompatible,
        update: int = 0,
    ) -> int:
        """Insert integer based on the provided type and start.

        The handling is based on the type:
        * ``b``: odd numbers are inserted as true and even numbers as false.
        * ``u(MAX)``: number is inserted as is.
        * ``u(MIN,MAX)``: number is inserted minus the ``MIN``.
        * ``i[]``: number is inserted as is.

        :param value: The value to be set in the bitfield.
        :param start: Bit offset to the type.
        :param tp: Type of the value to be deposited.
        :param update: The value to be updated with passed value. This allows
          actual cumulation of values in the bitfield's value.
        :raise ValueError: In case passed value is invalid for the given type
          or if type is not supported in Bitfield at all.
        """
        bitsize = cls.bitsize(tp)
        if msg := tp.validate(value):
            raise ValueError(msg)
        match tp:
            case RpcTypeBool():
                rvalue = 1 if value else 0
            case RpcTypeUnsigned():
                assert isinstance(value, SHVUInt)
                rvalue = int(value) - tp.minimum
            case RpcTypeEnum():
                assert isinstance(value, int)
                rvalue = value
            case _:  # pragma: no cover
                raise NotImplementedError
        mask: int = 2**bitsize - 1
        if rvalue != rvalue & mask:  # pragma: no cover
            raise RuntimeError("Value won't fit but is valid: implementation error")
        return (update ^ update & mask << start) | rvalue << start
