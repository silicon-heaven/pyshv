"""Python implementation of Silicon Heaven."""
from .chainpack import ChainPack, ChainPackReader, ChainPackWriter
from .cpon import Cpon, CponReader, CponWriter
from .rpcclient import (
    RpcClient,
    RpcClientPipe,
    RpcClientTCP,
    RpcClientTTY,
    RpcClientUnix,
    connect_rpc_client,
)
from .rpcerrors import (
    RpcError,
    RpcErrorCode,
    RpcInternalError,
    RpcInvalidParamsError,
    RpcInvalidRequestError,
    RpcMethodCallCancelledError,
    RpcMethodCallExceptionError,
    RpcMethodCallTimeoutError,
    RpcMethodNotFoundError,
    RpcParseError,
)
from .rpclogin import rpclogin, rpclogin_url
from .rpcmessage import RpcMessage
from .rpcmethod import RpcMethodAccess, RpcMethodDesc, RpcMethodFlags
from .rpcprotocol import (
    RpcProtocolSerial,
    RpcProtocolSerialCRC,
    RpcProtocolStream,
    RpcTransportProtocol,
)
from .rpcserver import (
    RpcServer,
    RpcServerTCP,
    RpcServerTTY,
    RpcServerUnix,
    create_rpc_server,
)
from .rpcsubscription import RpcSubscription
from .rpcurl import RpcLoginType, RpcProtocol, RpcUrl
from .shvversion import SHV_VERSION_MAJOR, SHV_VERSION_MINOR
from .simpleclient import SimpleClient
from .simpledevice import SimpleDevice
from .value import (
    SHVBool,
    SHVBoolType,
    SHVBytes,
    SHVDatetime,
    SHVDecimal,
    SHVFloat,
    SHVIMap,
    SHVIMapType,
    SHVInt,
    SHVList,
    SHVListType,
    SHVMap,
    SHVMapType,
    SHVMeta,
    SHVMetaType,
    SHVNull,
    SHVNullType,
    SHVStr,
    SHVType,
    SHVUInt,
    decimal_rexp,
    is_shvbool,
    is_shvimap,
    is_shvmap,
    is_shvnull,
    shvmeta,
    shvmeta_eq,
)
from .value_tools import SHVGetKey, shvget
from .valueclient import ValueClient

VERSION = (
    (__import__("pathlib").Path(__file__).parent / "version").read_text("utf-8").strip()
)


__all__ = [
    # cpon
    "Cpon",
    "CponReader",
    "CponWriter",
    # chainpack
    "ChainPack",
    "ChainPackReader",
    "ChainPackWriter",
    # rpcclient
    "connect_rpc_client",
    "RpcClient",
    "RpcClientTCP",
    "RpcClientUnix",
    "RpcClientPipe",
    "RpcClientTTY",
    # rpcprotocol
    "RpcTransportProtocol",
    "RpcProtocolStream",
    "RpcProtocolSerial",
    "RpcProtocolSerialCRC",
    # rpcserver
    "create_rpc_server",
    "RpcServer",
    "RpcServerTCP",
    "RpcServerUnix",
    "RpcServerTTY",
    # rpcurl
    "RpcProtocol",
    "RpcLoginType",
    "RpcUrl",
    # rpcmessage
    "RpcMessage",
    # rpcmethod
    "RpcMethodFlags",
    "RpcMethodAccess",
    "RpcMethodDesc",
    # rpcerror
    "RpcErrorCode",
    "RpcError",
    "RpcInternalError",
    "RpcInvalidParamsError",
    "RpcInvalidRequestError",
    "RpcMethodCallCancelledError",
    "RpcMethodCallExceptionError",
    "RpcMethodCallTimeoutError",
    "RpcMethodNotFoundError",
    "RpcParseError",
    # rpclogin
    "rpclogin",
    "rpclogin_url",
    # rpcsubscription
    "RpcSubscription",
    # simpleclient
    "SimpleClient",
    # simpledevice
    "SimpleDevice",
    # valueclient
    "ValueClient",
    # value
    "SHVMeta",
    "shvmeta",
    "shvmeta_eq",
    "SHVNull",
    "is_shvnull",
    "SHVBool",
    "is_shvbool",
    "SHVInt",
    "SHVUInt",
    "SHVFloat",
    "SHVDecimal",
    "decimal_rexp",
    "SHVStr",
    "SHVBytes",
    "SHVDatetime",
    "SHVList",
    "SHVMap",
    "SHVIMap",
    "is_shvmap",
    "is_shvimap",
    "SHVType",
    "SHVNullType",
    "SHVBoolType",
    "SHVListType",
    "SHVMapType",
    "SHVIMapType",
    "SHVMetaType",
    # value_tools
    "shvget",
    "SHVGetKey",
    # shvversion
    "SHV_VERSION_MAJOR",
    "SHV_VERSION_MINOR",
]
