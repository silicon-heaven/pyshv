"""Types used in SHV RPC ``dir`` call for method description."""

from __future__ import annotations

import dataclasses
import enum
import functools
import typing

from .rpcaccess import RpcAccess
from .rpcparam import SHVGetKey, shvget, shvgett
from .value import SHVMapType, SHVType, is_shvimap, is_shvmap


@dataclasses.dataclass
class RpcDir:
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

    class Flag(enum.IntFlag):
        """Flags assigned to the SHV RPC methods."""

        NONE = 0
        NOT_CALLABLE = 1 << 0
        GETTER = 1 << 1
        SETTER = 1 << 2
        LARGE_RESULT_HINT = 1 << 3
        NOT_IDEMPOTENT = 1 << 4
        USER_ID_REQUIRED = 1 << 5
        IS_UPDATABLE = 1 << 6

    name: str
    flags: Flag = dataclasses.field(default=Flag(0))
    param: str = "n"
    result: str = "n"
    access: RpcAccess = RpcAccess.BROWSE
    signals: dict[str, str] = dataclasses.field(default_factory=dict)
    extra: dict[str, SHVType] = dataclasses.field(default_factory=dict)

    def to_shv(self, extra: bool = False) -> SHVType:
        """Convert to SHV RPC representation."""
        res: dict[int, SHVType] = {
            self.Key.NAME: self.name,
            self.Key.FLAGS: self.flags,
        }
        if self.param != "n":
            res[self.Key.PARAM] = self.param
        if self.result != "n":
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
    def from_shv(cls, value: SHVType) -> RpcDir:
        """Create from SHV RPC representation."""
        if not is_shvimap(value):
            raise ValueError(f"Expected IMap but got {value!r}.")
        raccess = shvget(value, SHVGetKey("access", cls.Key.ACCESS), cls.access)
        rsignals = shvget(
            value, SHVGetKey("source", cls.Key.SIGNALS), typing.cast(SHVMapType, {})
        )
        rextra = shvget(value, cls.Key.EXTRA, typing.cast(SHVMapType, {}))
        result: str = shvgett(value, cls.Key.RESULT, str, cls.result)
        return cls(
            name=shvgett(value, SHVGetKey("name", cls.Key.NAME), str, "UNSPECIFIED"),
            flags=cls.Flag(
                shvgett(value, SHVGetKey("flags", cls.Key.FLAGS), int, cls.flags)
            ),
            param=shvgett(value, cls.Key.PARAM, str, cls.param),
            result=result,
            access=RpcAccess(raccess)
            if isinstance(raccess, int)
            else RpcAccess.fromstr(raccess)
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
        param: str = "i(0,)|n",
        result: str = "?",
        access: RpcAccess = RpcAccess.READ,
        signal: bool | str = False,
        flags: Flag = Flag.NONE,
        description: str = "",
    ) -> RpcDir:
        """Create getter method description.

        :param name: Name of the method.
        :param param: Type of the parameter this getter expects.
        :param result: Type of the result this getter provides.
        :param access: Minimal granted access level for this getter.
        :param signal: Allows specifying property change signal. You can specify
          `True` to get default `"chng"` signal or you can specify custom signal
          name (should end with *chng*).
        :param flags: Flags assigned to the method. :py:data:`Flags.GETTER` is
          always set.
        :param description: Short description of the value.
        """
        return cls(
            name,
            cls.Flag.GETTER | flags,
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
        param: str = "?",
        result: str = "n",
        access: RpcAccess = RpcAccess.WRITE,
        flags: Flag = Flag.NONE,
        description: str = "",
    ) -> RpcDir:
        """Create setter method description.

        :param name: Name of the method.
        :param param: Type of the parameter this setter expects.
        :param result: Type of the result this setter provides.
        :param access: Minimal granted access level for this setter.
        :param flags: Flags assigned to the method.
        :param description: Short description of the value.
        """
        return cls(
            name,
            flags,
            param,
            result,
            access,
            extra={"description": description} if description else {},
        )

    @classmethod
    @functools.lru_cache(maxsize=1)
    def stddir(cls) -> RpcDir:
        """Get description of standard 'dir' method."""
        return cls("dir", param="n|b|s", result="[!dir]|b")

    @classmethod
    @functools.lru_cache(maxsize=1)
    def stdls(cls) -> RpcDir:
        """Get description of standard 'ls' method."""
        return cls("ls", param="s|n", result="[s]|b", signals={"lsmod": "{b}"})
