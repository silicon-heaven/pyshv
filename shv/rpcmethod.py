"""Types used in SHV RPC method description."""
import collections.abc
import dataclasses
import enum
import functools

from .value import SHVType


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

    def toimap(self) -> SHVType:
        """Convert method description to SHV Map."""
        res: dict[int, str | int] = {1: self.name, 2: self.flags}
        if self.param != "Null":
            res[3] = self.param
        if self.result != "Null":
            res[4] = self.result
        res[5] = RpcMethodAccess.tostr(self.access)
        return res

    def tomap(self) -> SHVType:
        """Convert method description to SHV Map."""
        res: dict[str, str | int] = {"name": self.name, "flags": self.flags}
        if self.param != "Null":
            res["param"] = self.param
        if self.result != "Null":
            res["result"] = self.result
        res["access"] = RpcMethodAccess.tostr(self.access)
        if self.description:
            res["description"] = self.description
        return res

    @classmethod
    def fromSHV(cls, desc: SHVType) -> "RpcMethodDesc":
        """Convert SHV method description to this object representation."""
        if not isinstance(desc, collections.abc.Mapping):
            raise ValueError(f"Not valid method description: {repr(desc)}")
        rest: dict[str | int, SHVType] = {
            k: v for k, v in desc.items() if isinstance(k, (int, str))
        }
        name = rest.pop(1, rest.pop("name", None))
        flags = rest.pop(2, rest.pop("flags", 0))
        param = rest.pop(3, rest.pop("param", "Null"))
        result = rest.pop(4, rest.pop("result", "Null"))
        access = rest.pop(5, rest.pop("access", "bws"))
        description = rest.pop("description", "")
        if not isinstance(name, str):
            raise ValueError(f"Invalid method name format: {repr(name)}")
        return cls(
            name=name,
            flags=RpcMethodFlags(flags),
            param=param,
            result=result,
            access=RpcMethodAccess.fromstr(access),
            description=description,
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
