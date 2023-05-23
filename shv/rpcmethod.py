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
