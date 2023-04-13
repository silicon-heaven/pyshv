"""RPC protocols supported by RpcClient and RpcServer."""
import enum


class RpcProtocol(enum.Enum):
    """Enum of supported RPC protocols by this Python implementation."""

    TCP = enum.auto()
    LOCAL_SOCKET = enum.auto()
