"""Tools to convert between complex Python types and SHV types."""
from __future__ import annotations

import collections.abc
import typing

from .value import SHVType

SHVT = typing.TypeVar("SHVT", bound=SHVType)


class NoDefaultType:
    """Type for :var:`NO_DEFAULT` singleton."""

    def __new__(cls) -> NoDefaultType:
        if not hasattr(cls, "instance"):
            cls.instance = super(NoDefaultType, cls).__new__(cls)
        return cls.instance


NO_DEFAULT = NoDefaultType()
"""Singleton used to identify that there is no default."""


class SHVGetKey(typing.NamedTuple):
    """Key used in :func:`shvget` to allow both IMap as well as Map."""

    skey: str | None = None
    ikey: int | None = None


def shvget(
    value: SHVType,
    key: str | int | SHVGetKey | collections.abc.Sequence[str | int | SHVGetKey],
    default: SHVT | NoDefaultType = NO_DEFAULT,
) -> SHVType:
    """Get value from (i)map or (i)map of (i)maps or default.

    It is very common to query SHVType for keys and support both IMap as well as
    Map at the same time. This can be any number of nested Maps or IMaps. This
    simplifies access for such types.

    :param value: Some Map or IMap to be accessed
    :param key: Key or list of keys that should be recursively applied to the
      value.
    :param default: Default value used if value is not present.
      :class:`ValueError` is raised instead if :var:`NO_DEFAULT` is specifiedl.
    :return: extracted value or default.
    :raise ValueError: if the value is not present and no default provided.
    """
    for k in [key] if isinstance(key, (str, int, SHVGetKey)) else key:
        if not isinstance(value, collections.abc.Mapping):
            break
        vmap = typing.cast(collections.abc.Mapping[str | int, SHVType], value)
        if isinstance(k, SHVGetKey) and k.ikey is not None and k.ikey in vmap:
            value = vmap[k.ikey]
        elif isinstance(k, SHVGetKey) and k.skey is not None and k.skey in vmap:
            value = vmap[k.skey]
        elif isinstance(k, (str, int)) and k in vmap:
            value = vmap[k]
        else:
            if isinstance(default, NoDefaultType):
                raise ValueError(f"Missing key: {k}")
            value = default
            break
    if value is None and not isinstance(default, NoDefaultType):
        return default  # None is alias for not present for us
    return value


def shvgett(
    value: SHVType,
    key: str | int | SHVGetKey | collections.abc.Sequence[str | int | SHVGetKey],
    tp: type[SHVT],
    default: SHVT | NoDefaultType = NO_DEFAULT,
) -> SHVT:
    """Variant of :func:`shvget` that also checks for type.

    It is very common to query SHVType for keys and expecting a specific type or
    using default value if it is present or is of invalid type. It is a fails
    safe approach.

    :param value: Some Map or IMap to be accessed
    :param key: Key or list of keys that should be recursively applied to the
      value.
    :param tp: Type of the expected value.
    :param default: Default value used if value is not present.
      :class:`ValueError` is raised instead if :var:`NO_DEFAULT` is specifiedl.
    :return: extracted value or default.
    :raise ValueError: if the value is not present and no default provided.
    """
    res = shvget(value, key, default)
    if not isinstance(res, tp):
        raise ValueError(f"Invalid type: {value!r}")
    return res


def shvarg(
    value: SHVType,
    index: int,
    default: SHVT | NoDefaultType = NO_DEFAULT,
) -> SHVType:
    """Get value from list or default.

    Some methods expect sequence of values (tuples) as their parameters. This
    helps with parsing such value.

    :param value: Some List to be sanitized.
    :param index: The index in list we want to access.
    :param default: Default value used if value is not present.
      :class:`ValueError` is raised instead if :var:`NO_DEFAULT` is specifiedl.
    :return: extracted value or default.
    :raise ValueError: if the value is not present and no default provided.
    """
    if not isinstance(value, (collections.abc.Sequence, type(None))):
        raise ValueError(f"Invalid type: {value!r}")
    if value is not None and len(value) >= index and (res := value[index]) is not None:
        return res
    if isinstance(default, NoDefaultType):
        raise ValueError(f"Field {index} not provided")
    return default


def shvargt(
    value: SHVType,
    index: int,
    tp: type[SHVT],
    default: SHVT | NoDefaultType = NO_DEFAULT,
) -> SHVT:
    """Variant of :func:`shvarg` that also checks for type.

    :param value: Some List to be sanitized.
    :param index: The index in list we want to access.
    :param tp: Type of the expected value.
    :param default: Default value used if value is not present.
      :class:`ValueError` is raised instead if :var:`NO_DEFAULT` is specifiedl.
    :return: extracted value or default.
    :raise ValueError: if the value is not present and no default provided.
    """
    res = shvarg(value, index, default)
    if not isinstance(res, tp):
        raise ValueError(f"Invalid type: {res!r}")
    return res
