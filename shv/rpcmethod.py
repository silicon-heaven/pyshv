"""Types used in SHV RPC method description."""
import collections.abc
import dataclasses
import enum
import functools
import typing

from .value import SHVType
from .value_tools import SHVGetKey, shvget


class RpcMethodFlags(enum.IntFlag):
    """Flags assigned to the SHV RPC methods."""

    SIGNAL = 1 << 0
    GETTER = 1 << 1
    SETTER = 1 << 2
    LARGE_RESULT_HINT = 1 << 3


class RpcMethodAccess(enum.IntEnum):
    """Method access level."""

    BROWSE = enum.auto()
    READ = enum.auto()
    WRITE = enum.auto()
    COMMAND = enum.auto()
    CONFIG = enum.auto()
    SERVICE = enum.auto()
    SUPER_SERVICE = enum.auto()
    DEVEL = enum.auto()
    ADMIN = enum.auto()

    @classmethod
    @functools.cache
    def strmap(cls) -> dict[str, "RpcMethodAccess"]:
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
        return {v.value: k for k, v in cls.strmap().items()}

    def tostr(self) -> str:
        """Convert to string representation."""
        return self.strrmap().get(self.value, "bws")

    @classmethod
    def fromstr(cls, access: str) -> "RpcMethodAccess":
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

    name: str
    flags: RpcMethodFlags = RpcMethodFlags(0)
    param: str = "Null"
    result: str = "Null"
    access: RpcMethodAccess = RpcMethodAccess.BROWSE
    description: str = ""

    def toshv(self, use_map: bool = False) -> SHVType:
        """Convert to SHV RPC representation."""
        res: dict[int | str, SHVType] = {
            "name" if use_map else 1: self.name,
            "flags" if use_map else 2: self.flags,
        }
        if self.param != "Null":
            res["param" if use_map else 3] = self.param
        if self.result != "Null":
            res["result" if use_map else 4] = self.result
        res["access" if use_map else 5] = RpcMethodAccess.tostr(self.access)
        if self.description and use_map:
            res["description"] = self.description
        return typing.cast(SHVType, res)

    @classmethod
    def fromshv(cls, value: SHVType) -> "RpcMethodDesc":
        """Create from SHV RPC representation."""
        if not isinstance(value, collections.abc.Mapping):
            raise ValueError("Expected mapping.")
        return cls(
            name=shvget(value, SHVGetKey("name", 1), str, "UNSPECIFIED"),
            flags=RpcMethodFlags(shvget(value, SHVGetKey("flags", 2), int, cls.flags)),
            param=shvget(value, SHVGetKey("param", 3), str, cls.param),
            result=shvget(value, SHVGetKey("result", 4), str, cls.result),
            access=RpcMethodAccess.fromstr(
                shvget(value, SHVGetKey("access", 5), str, cls.access.tostr())
            ),
            description=shvget(value, "description", str, cls.description),
        )

    @classmethod
    def getter(
        cls,
        name: str = "get",
        param: str = "Int",
        result: str = "Any",
        access: RpcMethodAccess = RpcMethodAccess.READ,
        description: str = "",
    ) -> "RpcMethodDesc":
        """New getter method description.

        :param name: Name of the method.
        :param param: Type of the parameter this getter expects.
        :param result: Type of the result this getter provides.
        :param access: Minimal granted access level for this getter.
        :param description: Short description of the value.
        """
        return cls(name, RpcMethodFlags.GETTER, param, result, access, description)

    @classmethod
    def setter(
        cls,
        name: str = "set",
        param: str = "Any",
        result: str = "Null",
        access: RpcMethodAccess = RpcMethodAccess.WRITE,
        description: str = "",
    ) -> "RpcMethodDesc":
        """New setter method description.

        :param name: Name of the method.
        :param param: Type of the parameter this setter expects.
        :param result: Type of the result this setter provides.
        :param access: Minimal granted access level for this setter.
        :param description: Short description of the value.
        """
        return cls(name, RpcMethodFlags.SETTER, param, result, access, description)

    @classmethod
    def signal(
        cls,
        name: str = "chng",
        param: str = "Any",
        access: RpcMethodAccess = RpcMethodAccess.READ,
        description: str = "",
    ) -> "RpcMethodDesc":
        """New signal method description.

        :param name: Name of the method.
        :param param: Type of the parameter this signal carries.
        :param access: Minimal granted access level for this setter.
        :param description: Short description of the value.
        """
        return cls(name, RpcMethodFlags.SIGNAL, "Null", param, access, description)

    @classmethod
    @functools.lru_cache(maxsize=1)
    def stddir(cls) -> "RpcMethodDesc":
        """Get description of standard 'dir' method."""
        return cls("dir", param="idir", result="odir")

    @classmethod
    @functools.lru_cache(maxsize=1)
    def stdls(cls) -> "RpcMethodDesc":
        """Get description of standard 'ls' method."""
        return cls("ls", param="ils", result="ols")

    @classmethod
    @functools.lru_cache(maxsize=1)
    def stdlschng(cls) -> "RpcMethodDesc":
        """Get description of standard 'lschng' signal method."""
        return cls.signal("lschng", "olschng", RpcMethodAccess.BROWSE)
