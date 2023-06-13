"""Types used in SHV RPC method description."""
import collections.abc
import dataclasses
import enum
import functools

from .value import SHVType


class RpcMethodSignature(enum.IntEnum):
    """Signature of the SHV RPC method."""

    VOID_VOID = 0
    VOID_PARAM = 1
    RET_VOID = 2
    RET_PARAM = 3


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
    signature: RpcMethodSignature = RpcMethodSignature.VOID_VOID
    flags: RpcMethodFlags = RpcMethodFlags(0)
    access: RpcMethodAccess = RpcMethodAccess.BROWSE
    description: str = ""

    def tomap(self) -> SHVType:
        """Convert method description to SHV Map."""
        return {
            "name": self.name,
            "signature": self.signature,
            "flags": self.flags,
            "accessGrant": RpcMethodAccess.tostr(self.access),
            **({"description": self.description} if self.description else {}),
        }

    @classmethod
    def frommap(cls, desc: SHVType) -> "RpcMethodDesc":
        """Convert SHV method description to ."""
        if not isinstance(desc, collections.abc.Mapping):
            raise ValueError(f"Not valid method description: {repr(desc)}")
        name = desc.get("name", None)
        signature = desc.get("signature", None)
        flags = desc.get("flags", None)
        access = desc.get("accessGrant", None)
        if not isinstance(name, str):
            raise ValueError(f"Invalid method name format: {repr(name)}")
        return cls(
            name=name,
            signature=RpcMethodSignature(
                signature if isinstance(signature, int) else 0
            ),
            flags=RpcMethodFlags(flags if isinstance(flags, int) else 0),
            access=RpcMethodAccess.fromstr(
                access if isinstance(access, str) else "bws"
            ),
        )

    @classmethod
    def getter(
        cls,
        name: str = "get",
        access: RpcMethodAccess = RpcMethodAccess.READ,
        description: str = "",
    ) -> "RpcMethodDesc":
        """New getter method description.

        :param name: Name of the method.
        :param access: Minimal granted access level for this getter.
        :param description: Short description of the value.
        """
        return cls(
            name,
            RpcMethodSignature.RET_VOID,
            RpcMethodFlags.GETTER,
            access,
            description,
        )

    @classmethod
    def setter(
        cls,
        name: str = "set",
        access: RpcMethodAccess = RpcMethodAccess.WRITE,
        description: str = "",
    ) -> "RpcMethodDesc":
        """New setter method description.

        :param name: Name of the method.
        :param access: Minimal granted access level for this setter.
        :param description: Short description of the value.
        """
        return cls(
            name,
            RpcMethodSignature.VOID_PARAM,
            RpcMethodFlags.SETTER,
            access,
            description,
        )

    @classmethod
    def signal(
        cls,
        name: str = "chng",
        access: RpcMethodAccess = RpcMethodAccess.WRITE,
        description: str = "",
    ) -> "RpcMethodDesc":
        """New signal method description.

        :param name: Name of the method.
        :param access: Minimal granted access level for this setter.
        :param description: Short description of the value.
        """
        return cls(
            name,
            RpcMethodSignature.RET_VOID,
            RpcMethodFlags.SIGNAL,
            access,
            description,
        )
