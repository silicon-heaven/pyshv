"""Types used in SHV RPC method description."""

from __future__ import annotations

import collections.abc
import dataclasses
import enum
import functools
import typing

from .rpcparam import SHVGetKey, shvget, shvgett
from .value import SHVMapType, SHVType, is_shvmap


class RpcMethodFlags(enum.IntFlag):
    """Flags assigned to the SHV RPC methods."""

    NOT_CALLABLE = 1 << 0
    GETTER = 1 << 1
    SETTER = 1 << 2
    LARGE_RESULT_HINT = 1 << 3
    NOT_IDEMPOTENT = 1 << 4
    USER_ID_REQUIRED = 1 << 5


class RpcMethodAccess(enum.IntEnum):
    """Method access level."""

    BROWSE = 1
    READ = 8
    WRITE = 16
    COMMAND = 24
    CONFIG = 32
    SERVICE = 40
    SUPER_SERVICE = 48
    DEVEL = 56
    ADMIN = 63

    @classmethod
    @functools.cache
    def strmap(cls) -> dict[str, RpcMethodAccess]:
        """Map from string to this enum."""
        return {
            "bws": cls.BROWSE,
            "rd": cls.READ,
            "wr": cls.WRITE,
            "cmd": cls.COMMAND,
            "cfg": cls.CONFIG,
            "srv": cls.SERVICE,
            "ssrv": cls.SUPER_SERVICE,
            "dev": cls.DEVEL,
            "su": cls.ADMIN,
        }

    @classmethod
    @functools.cache
    def strrmap(cls) -> dict[int, str]:
        """Map from this enum to string."""
        return {v.value: k for k, v in cls.strmap().items()}

    def tostr(self) -> str:
        """Convert to string representation."""
        return self.strrmap().get(self.value, "bws")

    @classmethod
    def fromstr(cls, access: str) -> RpcMethodAccess:
        """Convert to string representation."""
        return cls.strmap().get(access, cls.BROWSE)


@dataclasses.dataclass
class RpcMethodDesc:
    """Description of the SHV RPC method.

    This is implemented as :func:`dataclasses.dataclass`.

    :param name: Name of the method.
    :param flags: Flags assigned to the method.
    :param param: Parameter type that should be provided to the method.
    :param result: Result type that is provided by the method.
    :param access: Minimal granted access level for this method.
    :param signals: Mapping of signal name to data type they cary. These are
      signals emited by this method.
    :param extra: Additional fields to be provied in some cases. The most common
      one is ``"description"`` with method description.
    """

    class Key(enum.IntEnum):
        """Key in the description IMap."""

        NAME = 1
        FLAGS = 2
        PARAM = 3
        RESULT = 4
        ACCESS = 5
        SIGNALS = 6
        EXTRA = 63

    name: str
    flags: RpcMethodFlags = dataclasses.field(default=RpcMethodFlags(0))
    param: str = "Null"
    result: str = "Null"
    access: RpcMethodAccess = RpcMethodAccess.BROWSE
    signals: dict[str, str] = dataclasses.field(default_factory=dict)
    extra: dict[str, SHVType] = dataclasses.field(default_factory=dict)

    def to_shv(self, extra: bool = False) -> SHVType:
        """Convert to SHV RPC representation."""
        res: dict[int, SHVType] = {
            self.Key.NAME: self.name,
            self.Key.FLAGS: self.flags,
        }
        if self.param != "Null":
            res[self.Key.PARAM] = self.param
        if self.result != "Null":
            res[self.Key.RESULT] = self.result
        res[self.Key.ACCESS] = self.access
        if self.signals:
            res[self.Key.SIGNALS] = {
                k: None if v == self.result else v for k, v in self.signals.items()
            }
        if self.extra:
            res[self.Key.EXTRA] = self.extra
        return res

    @classmethod
    def from_shv(cls, value: SHVType) -> RpcMethodDesc:
        """Create from SHV RPC representation."""
        if not isinstance(value, collections.abc.Mapping):
            raise ValueError(f"Expected Map but got {value!r}.")
        raccess = shvget(value, SHVGetKey("access", cls.Key.ACCESS), cls.access)
        rsignals = shvget(
            value, SHVGetKey("source", cls.Key.SIGNALS), typing.cast(SHVMapType, {})
        )
        rextra = shvget(value, cls.Key.EXTRA, typing.cast(SHVMapType, {}))
        result: str = shvgett(value, cls.Key.RESULT, str, cls.result)
        return cls(
            name=shvgett(value, SHVGetKey("name", cls.Key.NAME), str, "UNSPECIFIED"),
            flags=RpcMethodFlags(
                shvgett(value, SHVGetKey("flags", cls.Key.FLAGS), int, cls.flags)
            ),
            param=shvgett(value, cls.Key.PARAM, str, cls.param),
            result=result,
            access=RpcMethodAccess(raccess)
            if isinstance(raccess, int)
            else RpcMethodAccess.fromstr(raccess)
            if isinstance(raccess, str)
            else cls.access,
            signals={
                k: (result if v is None else v)
                for k, v in rsignals.items()
                if v is None or isinstance(v, str)
            }
            if is_shvmap(rsignals)
            else {},
            extra=dict(rextra) if is_shvmap(rextra) else {},
        )

    @classmethod
    def getter(
        cls,
        name: str = "get",
        param: str = "Int",
        result: str = "Any",
        access: RpcMethodAccess = RpcMethodAccess.READ,
        signal: bool | str = False,
        description: str = "",
    ) -> RpcMethodDesc:
        """Create getter method description.

        :param name: Name of the method.
        :param param: Type of the parameter this getter expects.
        :param result: Type of the result this getter provides.
        :param access: Minimal granted access level for this getter.
        :param signal: Allows specifying property change signal. You can specify
          `True` to get default `"chng"` signal or you can specify custom signal
          name (should end with *chng*).
        :param description: Short description of the value.
        """
        return cls(
            name,
            RpcMethodFlags.GETTER,
            param,
            result,
            access,
            {"chng" if signal is True else signal: result} if signal else {},
            {"description": description} if description else {},
        )

    @classmethod
    def setter(
        cls,
        name: str = "set",
        param: str = "Any",
        result: str = "Null",
        access: RpcMethodAccess = RpcMethodAccess.WRITE,
        description: str = "",
    ) -> RpcMethodDesc:
        """Create setter method description.

        :param name: Name of the method.
        :param param: Type of the parameter this setter expects.
        :param result: Type of the result this setter provides.
        :param access: Minimal granted access level for this setter.
        :param description: Short description of the value.
        """
        return cls(
            name,
            RpcMethodFlags.SETTER,
            param,
            result,
            access,
            extra={"description": description} if description else {},
        )

    @classmethod
    @functools.lru_cache(maxsize=1)
    def stddir(cls) -> RpcMethodDesc:
        """Get description of standard 'dir' method."""
        return cls("dir", param="idir", result="odir")

    @classmethod
    @functools.lru_cache(maxsize=1)
    def stdls(cls) -> RpcMethodDesc:
        """Get description of standard 'ls' method."""
        return cls("ls", param="ils", result="ols", signals={"lsmod": "olsmod"})
