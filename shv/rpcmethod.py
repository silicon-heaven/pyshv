"""Types used in SHV RPC method description."""
import enum


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
    def tostr(cls, access: "RpcMethodAccess") -> str:
        """Convert to string representation."""
        return {
            cls.BROWSE: "bws",
            cls.READ: "rd",
            cls.WRITE: "wr",
            cls.COMMAND: "cmd",
            cls.CONFIG: "cfg",
            cls.SERVICE: "srv",
            cls.SUPER_SERVICE: "ssrv",
            cls.DEVEL: "dev",
            cls.ADMIN: "su",
        }.get(access, "bws")

    @classmethod
    def fromstr(cls, access: str) -> "RpcMethodAccess":
        """Convert to string representation."""
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
        }.get(access, cls.BROWSE)
