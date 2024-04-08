"""Values used in SHV communication."""

import abc
import collections.abc
import datetime
import decimal
import functools
import itertools
import typing

SHVNullType: typing.TypeAlias = typing.Union[None, "SHVNull"]
SHVBoolType: typing.TypeAlias = typing.Union[bool, "SHVBool"]
SHVListType: typing.TypeAlias = collections.abc.Sequence["SHVType"]
SHVMapType: typing.TypeAlias = collections.abc.Mapping[str, "SHVType"]
SHVIMapType: typing.TypeAlias = collections.abc.Mapping[int, "SHVType"]
SHVType: typing.TypeAlias = (
    SHVNullType
    | SHVBoolType
    | int
    | float
    | decimal.Decimal
    | bytes
    | str
    | datetime.datetime
    | SHVListType
    | SHVMapType
    | SHVIMapType
    | SHVIMapType
    | SHVMapType
)
SHVMetaType: typing.TypeAlias = collections.abc.MutableMapping[int | str, SHVType]


class SHVMeta(abc.ABC):  # noqa B024
    """SHV values can have meta with attributes associated with them.

    This provides meta attribute that can be added to other types. Only create
    class that has as parent this class and the class you want to wrap. The
    SHVMeta provides you with meta attribute that you can use to store and
    access meta attributes. Thanks to it being both parent of SHVMeta as well as
    original type you can use isinstance to detect type. For example to check if
    type is `int` you can use ``isinstance(foo, int)``.

    .. warning::
        ``None`` and bool can't have meta assigned to the them just by simple
        inheritance and thus we define our custom types. Make sure that you
        always expect that you can get instance of :class:`SHVNull` instead of
        ``None`` and :class:`SHVBool` instead of ``True`` and ``False``.
    .. note::
        Meta is not intentionally included in the plain comparison to ensure
        that standard hashable types are still hashable while meta is
        modifiable. You can use :func:`shvmeta_eq` to compare with meta.
    """

    @property
    def meta(self) -> SHVMetaType:
        """Meta attributes for this SHV type."""
        if not hasattr(self, "_meta"):
            self._meta: SHVMetaType = {}
        return typing.cast(SHVMetaType, self._meta)

    @staticmethod
    def new(value: object, meta: SHVMetaType | None = None) -> SHVType:
        """Create new value with given meta.

        This select an appropriate class based on the value passed.

        You can also use it to set meta value to newly created object because
        when `value` is of `SHVMeta` it returns the same object and only updates
        provided meta.
        """
        res: SHVMeta
        if isinstance(value, SHVMeta):
            res = value
        elif value is None:
            res = SHVNull()
        elif isinstance(value, bool):
            res = SHVBool(value)
        elif isinstance(value, int):
            res = SHVInt(value)
        elif isinstance(value, float):
            res = SHVFloat(value)
        elif isinstance(value, bytes):
            res = SHVBytes(value)
        elif isinstance(value, str):
            res = SHVStr(value)
        elif isinstance(value, datetime.datetime):
            res = SHVDatetime.fromtimestamp(value.timestamp(), value.tzinfo)
        elif isinstance(value, decimal.Decimal):
            res = SHVDecimal(value)
        elif isinstance(value, collections.abc.Sequence):
            res = SHVList(value)
        elif is_shvimap(value):
            res = SHVIMap(value)
        elif is_shvmap(value):
            res = SHVMap(value)
        else:
            raise ValueError(f"Invalid SHV value: {value!r}")
        if meta:
            res.meta.update(meta)
        return typing.cast(SHVType, res)


def shvmeta(value: object) -> SHVMetaType:
    """Get SHV Meta or provide empty dict as a fallback."""
    if isinstance(value, SHVMeta):
        return value.meta
    return {}


def shvmeta_eq(v1: object, v2: object) -> bool:
    """Perform comparison including the :class:`SHVMeta` not just plain values."""
    if shvmeta(v1) != shvmeta(v2):
        return False
    if isinstance(v1, SHVUInt) != isinstance(v2, SHVUInt):
        return False
    if (
        isinstance(v1, collections.abc.Sequence)
        and isinstance(v2, collections.abc.Sequence)
        and not (isinstance(v1, str | bytes) or isinstance(v2, str | bytes))
    ):
        return len(v1) == len(v2) and all(
            shvmeta_eq(v1[i], v2[i]) for i in range(len(v1))
        )
    if isinstance(v1, collections.abc.Mapping) and isinstance(
        v2, collections.abc.Mapping
    ):
        return all(
            k in v1 and k in v2 and shvmeta_eq(v1[k], v2[k])
            for k in set(itertools.chain(v1.keys(), v2.keys()))
        )
    return bool(v1 == v2)


class SHVNull(SHVMeta):
    """Null (None) with :class:`SHVMeta`."""

    def __bool__(self) -> bool:
        return False

    def __eq__(self, value: object) -> bool:
        return value is None or isinstance(value, SHVNull)

    def __hash__(self) -> int:
        return hash(None)


def is_shvnull(value: object) -> typing.TypeGuard[SHVNullType]:
    """Validate type of the value as either ``None`` or :class:`SHVNull`."""
    return value is None or isinstance(value, SHVNull)


class SHVBool(SHVMeta):
    """Boolean with :class:`SHVMeta`."""

    def __init__(self, value: bool) -> None:
        self._value = value

    def __bool__(self) -> bool:
        return self._value

    def __eq__(self, value: object) -> bool:
        return bool(value) is self._value

    def __hash__(self) -> int:
        return hash(self._value)


def is_shvbool(value: object) -> typing.TypeGuard[bool | SHVBool]:
    """Validate type of value as either :class:`bool` or :class:`SHVBool`."""
    return isinstance(value, bool | SHVBool)


class SHVInt(int, SHVMeta):
    """Integer with class:`SHVMeta`."""


class SHVUInt(int, SHVMeta):
    """Unsigned integer with :class:`SHVMeta`.

    There is no unsigned type in Python and thus compared to :class:`SHVInt`
    (that can be interchanged with `int`) you have to always use this class to
    represent unsigned integer.
    """


class SHVFloat(float, SHVMeta):
    """Float with :class:`SHVMeta`."""


class SHVDecimal(decimal.Decimal, SHVMeta):
    """Decimal with :class:`SHVMeta`."""


def decimal_rexp(value: decimal.Decimal) -> tuple[int, int]:
    """Decomposes decimal number to the mantissa and exponent.

    Python's Decimal does not directly provides a way to get mantissa and exponent. In
    SHV it is the preferred way to store decimal numbers and this this functions is
    provided for that.

    :param value: Decimal number to be decomposed to mantissa and exponent.
    :returns: Tuple with mantissa and decimal exponent.
    """
    t = value.as_tuple()
    mantissa = functools.reduce(
        lambda a, b: a + (b[1] * 10 ** b[0]), enumerate(reversed(t.digits)), 0
    ) * (-1 if t.sign else 1)
    assert isinstance(t.exponent, int)
    return mantissa, t.exponent


class SHVBytes(bytes, SHVMeta):
    """Bytes with :class:`SHVMeta`."""


class SHVStr(str, SHVMeta):
    """String with :class:`SHVMeta`."""


class SHVDatetime(datetime.datetime, SHVMeta):
    """Date and time with :class:`SHVMeta`."""


class SHVList(list[SHVType], SHVMeta):
    """List of :class:`SHVMeta` values."""


class SHVMap(dict[str, SHVType], SHVMeta):
    """Dictionary with :class:`SHVMeta`."""


class SHVIMap(dict[int, SHVType], SHVMeta):
    """Dictionary with :class:`SHVMeta`."""


def is_shvlist(value: object) -> typing.TypeGuard[SHVListType]:
    """Check if given value can be SHV List."""
    return isinstance(value, collections.abc.Sequence) and all(
        is_shvtype(v) for v in value
    )


def is_shvmap(value: object) -> typing.TypeGuard[SHVMapType]:
    """Check if given value can be SHV Map."""
    return isinstance(value, collections.abc.Mapping) and all(
        isinstance(k, str) and is_shvtype(v) for k, v in value.items()
    )


def is_shvimap(value: object) -> typing.TypeGuard[SHVIMapType]:
    """Check if given value can be SHV IMap."""
    return isinstance(value, collections.abc.Mapping) and all(
        isinstance(k, int) and is_shvtype(v) for k, v in value.items()
    )


def is_shvtype(value: object) -> typing.TypeGuard[SHVType]:
    """Validate type of the value as SHVType."""
    return (
        is_shvnull(value)
        or is_shvbool(value)
        or isinstance(
            value, int | float | decimal.Decimal | bytes | str | datetime.datetime
        )
        or is_shvlist(value)
        or is_shvimap(value)
        or is_shvmap(value)
    )
