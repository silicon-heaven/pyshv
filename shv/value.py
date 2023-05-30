"""Values used in SHV communication."""
import abc
import collections.abc
import datetime
import decimal
import itertools
import typing

SHVType: typing.TypeAlias = typing.Union[
    None,
    bool,
    int,
    float,
    decimal.Decimal,
    bytes,
    str,
    datetime.datetime,
    collections.abc.Sequence["SHVType"],
    collections.abc.Mapping[str | int, "SHVType"],
    "SHVMeta",
]
SHVMetaType: typing.TypeAlias = dict[int | str, SHVType]


class SHVMeta(abc.ABC):
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
            setattr(self, "_meta", {})
        return getattr(self, "_meta")

    @staticmethod
    def new(value: typing.Any, meta: SHVMetaType | None = None) -> "SHVMeta":
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
        elif isinstance(value, list):
            res = SHVList(value)
        elif isinstance(value, dict):
            res = SHVDict(value)
        else:
            raise ValueError(f"Invalid SHV value: {repr(value)}")
        if meta:
            res.meta.update(meta)
        return res


def shvmeta(value: SHVType) -> SHVMetaType:
    """Get SHV Meta or provide empty dict as a fallback."""
    if isinstance(value, SHVMeta):
        return value.meta
    return {}


def shvmeta_eq(v1: typing.Any, v2: typing.Any) -> bool:
    """Perform comparison including the :class:`SHVMeta` not just plain values."""
    if shvmeta(v1) != shvmeta(v2):
        return False
    if isinstance(v1, SHVUInt) != isinstance(v2, SHVUInt):
        return False
    if (
        isinstance(v1, collections.abc.Sequence)
        and isinstance(v2, collections.abc.Sequence)
        and not (isinstance(v1, (str, bytes)) or isinstance(v2, (str, bytes)))
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
    return v1 == v2


class SHVNull(SHVMeta):
    """Null (None) with :class:`SHVMeta`."""

    def __bool__(self) -> bool:
        return False

    def __eq__(self, value) -> bool:
        return value is None or isinstance(value, SHVNull)

    def __hash__(self) -> int:
        return hash(None)


def is_shvnull(value: typing.Any) -> bool:
    """Validate type of the value as either ``None`` or :class:`SHVNull`."""
    return value is None or isinstance(value, SHVNull)


class SHVBool(SHVMeta):
    """Boolean with :class:`SHVMeta`."""

    def __init__(self, value: bool):
        self._value = value

    def __bool__(self) -> bool:
        return self._value

    def __eq__(self, value) -> bool:
        return bool(value) is self._value

    def __hash__(self) -> int:
        return hash(self._value)


def is_shvbool(value: typing.Any) -> bool:
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


class SHVBytes(bytes, SHVMeta):
    """Bytes with :class:`SHVMeta`."""


class SHVStr(str, SHVMeta):
    """String with :class:`SHVMeta`."""


class SHVDatetime(datetime.datetime, SHVMeta):
    """Date and time with :class:`SHVMeta`."""


class SHVList(list[SHVType], SHVMeta):
    """List of :class:`SHVMeta` values."""


class SHVDict(dict[str | int, SHVType], SHVMeta):
    """Dictionary with :class:`SHVMeta`."""


def is_shvmap(value: typing.Any) -> bool:
    """Check if given value can be SHV Map."""
    return isinstance(value, collections.abc.Mapping) and all(
        isinstance(k, str) for k in value.keys()
    )


def is_shvimap(value: typing.Any) -> bool:
    """Check if given value can be SHV IMap."""
    return isinstance(value, collections.abc.Mapping) and all(
        isinstance(k, int) for k in value.keys()
    )


TSHVType = typing.TypeVar("TSHVType", bound=SHVType)


def shvget(
    value: SHVType,
    key: str | int | collections.abc.Sequence[str | int],
    default: TSHVType,
    tp: typing.Type[TSHVType],
) -> TSHVType:
    """Get value from possible (i)map or (i)map of (i)maps or default.

    It is very common to query SHVType for keys and expecting a specific type or using
    default value if it is present or is of invalid type. It is a fails safe approach.

    :param value: Some type to be accessed
    :param key: Key or list of keys that should be recursively applied to the value.
    :param default: Default value used if value is not present or is of invalid type.
    :param tp: Type of the expected value.
    """
    if not isinstance(key, (str, int)):
        if len(key) == 0:
            return value if isinstance(value, tp) else default
        if isinstance(value, collections.abc.Mapping):
            return shvget(value.get(key[0], {}), key[1:], default, tp)
        return default
    if isinstance(value, collections.abc.Mapping):
        res = value.get(key, default)
        return res if isinstance(res, tp) else default
    return default
