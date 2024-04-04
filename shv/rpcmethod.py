"""Types used in SHV RPC method description."""

from __future__ import annotations

import collections.abc
import dataclasses
import enum
import functools
import typing

from .rpcparams import SHVGetKey, shvget, shvgett
from .value import SHVType


class RpcMethodFlags(enum.IntFlag):
    """Flags assigned to the SHV RPC methods."""

    SIGNAL = 1 << 0
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
    :param signature: Calling signature for this method.
    :param flags: Flags assigned to the method.
    :param access: Minimal granted access level for this method.
    :param description: Short description of the method.
    """

    class Key(enum.IntEnum):
        """Key in the description IMap."""

        NAME = 1
        FLAGS = 2
        PARAM = 3
        RESULT = 4
        ACCESS = 5
        SOURCE = 6

    name: str
    flags: RpcMethodFlags = dataclasses.field(default=RpcMethodFlags(0))
    param: str = "Null"
    result: str = "Null"
    access: RpcMethodAccess = RpcMethodAccess.BROWSE
    source: list[str] = dataclasses.field(default_factory=list)
    description: str = ""

    def to_shv(self, use_map: bool = False) -> SHVType:
        """Convert to SHV RPC representation."""
        res: dict[int | str, SHVType] = {
            "name" if use_map else self.Key.NAME: self.name,
            "flags" if use_map else self.Key.FLAGS: self.flags,
        }
        if self.param != "Null":
            res["param" if use_map else self.Key.PARAM] = self.param
        if self.result != "Null":
            res["result" if use_map else self.Key.RESULT] = self.result
        res["access" if use_map else self.Key.ACCESS] = RpcMethodAccess.tostr(
            self.access
        )
        if self.source:
            res["source" if use_map else self.Key.SOURCE] = (
                self.source[0] if len(self.source) == 1 else self.source
            )
        if self.description and use_map:
            res["description"] = self.description
        return typing.cast(SHVType, res)

    @classmethod
    def from_shv(cls, value: SHVType) -> RpcMethodDesc:
        """Create from SHV RPC representation."""
        if not isinstance(value, collections.abc.Mapping):
            raise ValueError("Expected Map.")
        rsource = shvget(value, SHVGetKey("source", cls.Key.SOURCE), [])
        return cls(
            name=shvgett(value, SHVGetKey("name", cls.Key.NAME), str, "UNSPECIFIED"),
            flags=RpcMethodFlags(
                shvgett(value, SHVGetKey("flags", cls.Key.FLAGS), int, cls.flags)
            ),
            param=shvgett(value, SHVGetKey("param", cls.Key.PARAM), str, cls.param),
            result=shvgett(value, SHVGetKey("result", cls.Key.RESULT), str, cls.result),
            access=RpcMethodAccess.fromstr(
                shvgett(
                    value, SHVGetKey("access", cls.Key.ACCESS), str, cls.access.tostr()
                )
            ),
            source=[rsource]
            if isinstance(rsource, str)
            else [v for v in rsource if isinstance(v, str)]
            if isinstance(rsource, collections.abc.Sequence)
            else [],
            description=shvgett(value, "description", str, cls.description),
        )

    @classmethod
    def getter(
        cls,
        name: str = "get",
        param: str = "Int",
        result: str = "Any",
        access: RpcMethodAccess = RpcMethodAccess.READ,
        description: str = "",
    ) -> RpcMethodDesc:
        """Create getter method description.

        :param name: Name of the method.
        :param param: Type of the parameter this getter expects.
        :param result: Type of the result this getter provides.
        :param access: Minimal granted access level for this getter.
        :param description: Short description of the value.
        """
        return cls(name, RpcMethodFlags.GETTER, param, result, access, [], description)

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
        return cls(name, RpcMethodFlags.SETTER, param, result, access, [], description)

    @classmethod
    def signal(
        cls,
        name: str = "chng",
        source: list[str] | str = "get",
        param: str = "Any",
        access: RpcMethodAccess = RpcMethodAccess.READ,
        description: str = "",
    ) -> RpcMethodDesc:
        """Create signal method description.

        :param name: Name of the signal.
        :param source: Method(s) name signal is associated with.
        :param param: Type of the parameter this signal carries.
        :param access: Minimal granted access level for this setter.
        :param description: Short description of the value.
        """
        return cls(
            name,
            RpcMethodFlags.SIGNAL,
            "Null",
            param,
            access,
            [source] if isinstance(source, str) else source,
            description,
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
        return cls("ls", param="ils", result="ols")

    @classmethod
    @functools.lru_cache(maxsize=1)
    def stdlsmod(cls) -> RpcMethodDesc:
        """Get description of standard 'lsmod' signal method."""
        return cls.signal("lsmod", "ls", "olsmod", RpcMethodAccess.BROWSE)
