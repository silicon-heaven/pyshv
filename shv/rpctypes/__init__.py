"""Support for type definition in SHV RPC.

The support consists of the way to transform string representation from and to
python objects. These objects can be used to reason with provided type hint
info. They also support validation of the :class:`shv.SHVType`.
"""

from .any import RpcTypeAny, rpctype_any
from .base import RpcType
from .bitfield import (
    RpcTypeBitfield,
    RpcTypeBitfieldCompatible,
    RpcTypeBitfieldItem,
    SHVTypeBitfieldCompatible,
)
from .blob import RpcTypeBlob, rpctype_blob
from .bool import RpcTypeBool, rpctype_bool
from .datetime import RpcTypeDateTime, rpctype_datetime
from .decimal import RpcTypeDecimal, rpctype_decimal
from .double import RpcTypeDouble, rpctype_double
from .enum import RpcTypeEnum
from .imap import RpcTypeIMap, rpctype_imap
from .integer import RpcTypeInteger, rpctype_integer
from .keystruct import RpcTypeKeyStruct
from .list import RpcTypeList, rpctype_list
from .map import RpcTypeMap, rpctype_map
from .null import RpcTypeNull, rpctype_null
from .oneof import RpcTypeOneOf, RpcTypeOptional
from .parse import RpcTypeParseError, rpctype_parse
from .standard import (
    RpcTypeStandard,
    rpctype_alert,
    rpctype_clientinfo,
    rpctype_dir,
    rpctype_exchange_p,
    rpctype_exchange_r,
    rpctype_exchange_v,
    rpctype_get,
    rpctype_getlog_p,
    rpctype_getlog_r,
    rpctype_history_records,
    rpctype_stat,
)
from .string import RpcTypeString, rpctype_string
from .struct import RpcTypeStruct, RpcTypeStructItem
from .tuple import RpcTypeTuple, RpcTypeTupleItem
from .unsigned import RpcTypeUnsigned, rpctype_unsigned

__all__ = [
    "RpcType",
    "RpcTypeAny",
    "RpcTypeBitfield",
    "RpcTypeBitfieldCompatible",
    "RpcTypeBitfieldItem",
    "RpcTypeBlob",
    "RpcTypeBool",
    "RpcTypeDateTime",
    "RpcTypeDecimal",
    "RpcTypeDouble",
    "RpcTypeEnum",
    "RpcTypeIMap",
    "RpcTypeInteger",
    "RpcTypeKeyStruct",
    "RpcTypeList",
    "RpcTypeMap",
    "RpcTypeNull",
    "RpcTypeOneOf",
    "RpcTypeOptional",
    "RpcTypeParseError",
    "RpcTypeStandard",
    "RpcTypeString",
    "RpcTypeStruct",
    "RpcTypeStructItem",
    "RpcTypeTuple",
    "RpcTypeTupleItem",
    "RpcTypeUnsigned",
    "SHVTypeBitfieldCompatible",
    "rpctype_alert",
    "rpctype_any",
    "rpctype_blob",
    "rpctype_bool",
    "rpctype_clientinfo",
    "rpctype_datetime",
    "rpctype_decimal",
    "rpctype_dir",
    "rpctype_double",
    "rpctype_exchange_p",
    "rpctype_exchange_r",
    "rpctype_exchange_v",
    "rpctype_get",
    "rpctype_getlog_p",
    "rpctype_getlog_r",
    "rpctype_history_records",
    "rpctype_imap",
    "rpctype_integer",
    "rpctype_list",
    "rpctype_map",
    "rpctype_null",
    "rpctype_parse",
    "rpctype_stat",
    "rpctype_string",
    "rpctype_unsigned",
]
