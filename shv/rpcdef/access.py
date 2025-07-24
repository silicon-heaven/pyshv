"""The SHV RPC access levels."""

from __future__ import annotations

import enum
import functools


class RpcAccess(enum.IntEnum):
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
    def strmap(cls) -> dict[str, RpcAccess]:
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
    def fromstr(cls, access: str) -> RpcAccess:
        """Convert to string representation."""
        return cls.strmap().get(access, cls.BROWSE)
