"""Tools to convert between complex Python types and SHV types."""
import collections.abc
import typing

from . import tools
from .value import SHVType

SHVT = typing.TypeVar("SHVT", bound=SHVType)


class SHVGetKey(typing.NamedTuple):
    """Key used in :func:`shvget` to allow both IMap as well as Map."""

    skey: str | None = None
    ikey: int | None = None


def shvget(
    value: SHVType,
    key: str | int | SHVGetKey | collections.abc.Sequence[str | int | SHVGetKey],
    tp: typing.Type[SHVT],
    default: SHVT,
    raise_invalid: bool = False,
) -> SHVT:
    """Get value from (i)map or (i)map of (i)maps or default.

    It is very common to query SHVType for keys and expecting a specific type or using
    default value if it is present or is of invalid type. It is a fails safe approach.

    :param value: Some Map or IMap to be accessed
    :param key: Key or list of keys that should be recursively applied to the value.
    :param default: Default value used if value is not present or is of invalid type.
    :param tp: Type of the expected value.
    """
    keys = [key] if isinstance(key, (str, int, SHVGetKey)) else key
    for k, has_next in tools.lookahead(keys):
        if not isinstance(value, collections.abc.Mapping):
            break
        vmap = typing.cast(collections.abc.Mapping[str | int, SHVType], value)
        if isinstance(k, SHVGetKey):
            if k.skey is not None:
                value = vmap.get(k.skey, default)
            if k.ikey is not None:
                value = vmap.get(k.ikey, value)
        else:
            value = vmap.get(k, default)
        if not has_next:
            if not isinstance(value, tp):
                break
            return value
    if raise_invalid:
        raise ValueError("Invalid type")
    return default
