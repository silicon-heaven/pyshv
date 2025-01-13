"""The definition of standard SHV types."""

import typing

from .. import SHVType
from .any import rpctype_any
from .base import RpcType
from .bitfield import RpcTypeBitfield
from .blob import rpctype_blob
from .bool import rpctype_bool
from .datetime import rpctype_datetime
from .enum import RpcTypeEnum
from .imap import RpcTypeIMap
from .integer import RpcTypeInteger, rpctype_integer
from .list import RpcTypeList
from .map import RpcTypeMap, rpctype_map
from .null import rpctype_null
from .oneof import RpcTypeOneOf
from .string import rpctype_string
from .struct import RpcTypeStruct
from .unsigned import rpctype_unsigned


class RpcTypeStandard(RpcType):
    """The container for the types defined by standard."""

    def __init__(self, name: str, tp: RpcType) -> None:
        self._name = name
        self._tp = tp

    @property
    def name(self) -> str:
        """Name assigned to the standard type."""
        return self._name

    @property
    def type(self) -> RpcType:
        """Type this standard type represents."""
        return self._tp

    def __str__(self) -> str:
        return f"!{self._name}"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RpcTypeStandard)
            and self._name == other._name
            and self._tp == other._tp
        )

    def validate(self, value: SHVType) -> typing.TypeGuard[SHVType]:  # noqa: D102
        return self._tp.validate(value)


rpctype_dir = RpcTypeStandard(
    "dir",
    RpcTypeStruct({
        1: (rpctype_string, "name"),
        2: (
            RpcTypeBitfield(
                (1, rpctype_bool, "isGetter"),
                (2, rpctype_bool, "isSetter"),
                (3, rpctype_bool, "largeResult"),
                (4, rpctype_bool, "notIndempotent"),
                (5, rpctype_bool, "userIDRequired"),
            ),
            "flags",
        ),
        3: (RpcTypeOneOf(rpctype_string, rpctype_null), "paramType"),
        4: (RpcTypeOneOf(rpctype_string, rpctype_null), "resultType"),
        5: (RpcTypeOneOf(RpcTypeInteger(0, 63), rpctype_null), "accessLevel"),
        6: (RpcTypeOneOf(rpctype_string, rpctype_null), "signals"),
        63: (rpctype_map, "extra"),
    }),
)
"""
i{s:name:1,u[b:isGetter:1,b:isSetter,b:largeResult,b:notIndempotent,b:userIDRequired]|n:flags,s|n:paramType,s|n:resultType,i(0,63):accessLevel,{s|n}:signals,{?}:extra:63}|b
"""


rpctype_alert = RpcTypeStandard(
    "alert",
    RpcTypeStruct({
        0: (rpctype_datetime, "date"),
        1: (RpcTypeInteger(0, 63), "level"),
        2: (rpctype_string, "id"),
        3: (rpctype_any, "info"),
    }),
)
"""
i{t:date,i(0,63):level,s:id,?:info}
"""

rpctype_clientinfo = RpcTypeStandard(
    "clientInfo",
    RpcTypeStruct({
        1: (rpctype_integer, "clientId"),
        2: (RpcTypeOneOf(rpctype_string, rpctype_null), "userName"),
        3: (RpcTypeOneOf(rpctype_string, rpctype_null), "mountPoint"),
        4: (
            RpcTypeOneOf(
                RpcTypeMap(RpcTypeOneOf(rpctype_integer, rpctype_null)), rpctype_null
            ),
            "subscriptions",
        ),
        63: (rpctype_map, "extra"),
    }),
)
"""
i{i:clientId:1,s|n:userName,s|n:mountPoint,{i|n}|n:subscriptions,{?}:extra:63}
"""


rpctype_stat = RpcTypeStandard(
    "stat",
    RpcTypeStruct({
        0: (rpctype_integer, "type"),
        1: (rpctype_integer, "size"),
        2: (rpctype_integer, "pageSize"),
        3: (RpcTypeOneOf(rpctype_datetime, rpctype_null), "accessTime"),
        4: (RpcTypeOneOf(rpctype_datetime, rpctype_null), "modTime"),
        5: (RpcTypeOneOf(rpctype_integer, rpctype_null), "maxWrite"),
    }),
)
"""
i{i:type,i:size,i:pageSize,t|n:accessTime,t|n:modTime,i|n:maxWrite}
"""

rpctype_exchange_p = RpcTypeStandard(
    "exchangeP",
    RpcTypeStruct({
        0: (rpctype_unsigned, "counter"),
        1: (RpcTypeOneOf(rpctype_unsigned, rpctype_null), "readyToReceive"),
        3: (RpcTypeOneOf(rpctype_blob, rpctype_null), "data"),
    }),
)
"""
i{u:counter,u|n:readyToReceive,b|n:data:3}
"""

rpctype_exchange_r = RpcTypeStandard(
    "exchangeR",
    RpcTypeStruct({
        1: (RpcTypeOneOf(rpctype_unsigned, rpctype_null), "readyToReceive"),
        2: (RpcTypeOneOf(rpctype_unsigned, rpctype_null), "readyToSend"),
        3: (RpcTypeOneOf(rpctype_blob, rpctype_null), "data"),
    }),
)
"""
i{u|n:readyToReceive:1,u|n:readyToSend,b|n:data}
"""

rpctype_exchange_v = RpcTypeStandard(
    "exchangeV",
    RpcTypeStruct({
        1: (RpcTypeOneOf(rpctype_unsigned, rpctype_null), "readyToReceive"),
        2: (RpcTypeOneOf(rpctype_unsigned, rpctype_null), "readyToSend"),
    }),
)
"""
i{u|n:readyToReceive:1,u|n:readyToSend}
"""

rpctype_getlog_p = RpcTypeStandard(
    "getLogP",
    RpcTypeStruct({
        0: (RpcTypeOneOf(rpctype_datetime, rpctype_null), "since"),
        1: (RpcTypeOneOf(rpctype_datetime, rpctype_null), "until"),
        2: (RpcTypeOneOf(RpcTypeInteger(0), rpctype_null), "count"),
        3: (RpcTypeOneOf(rpctype_bool, rpctype_null), "snapshot"),
        4: (RpcTypeOneOf(rpctype_string, rpctype_null), "ri"),
    }),
)
"""
{t|n:since,t|n:until,i(0,)|n:count,b|n:snapshot,s|n:ri}
"""

rpctype_getlog_r = RpcTypeStandard(
    "getLogR",
    RpcTypeStruct({
        1: (rpctype_datetime, "timestamp"),
        2: (RpcTypeOneOf(RpcTypeInteger(0), rpctype_null), "ref"),
        3: (RpcTypeOneOf(rpctype_string, rpctype_null), "path"),
        4: (RpcTypeOneOf(rpctype_string, rpctype_null), "signal"),
        5: (RpcTypeOneOf(rpctype_string, rpctype_null), "source"),
        6: (rpctype_null, "value"),
        7: (RpcTypeOneOf(rpctype_string, rpctype_null), "userId"),
        8: (RpcTypeOneOf(rpctype_bool, rpctype_null), "repeat"),
    }),
)
"""
[i{t:timestamp:1,i(0,)|n:ref,s|n:path,s|n:signal,s|n:source,?:value,s|n:userId,b|n:repeat}]
"""


rpctype_history_records = RpcTypeStandard(
    "historyRecords",
    RpcTypeList(
        RpcTypeIMap(
            RpcTypeStruct({
                0: (
                    RpcTypeEnum({1: "normal", 2: "keep", 3: "timeJump", 4: "timeAbig"}),
                    "type",
                ),
                1: (rpctype_datetime, "timestamp"),
                2: (RpcTypeOneOf(rpctype_string, rpctype_null), "path"),
                3: (RpcTypeOneOf(rpctype_string, rpctype_null), "signal"),
                4: (RpcTypeOneOf(rpctype_string, rpctype_null), "source"),
                5: (rpctype_any, "value"),
                6: (RpcTypeInteger(0, 63), "accessLevel"),
                7: (RpcTypeOneOf(rpctype_string, rpctype_null), "userId"),
                8: (RpcTypeOneOf(rpctype_bool, rpctype_null), "repeat"),
                60: (RpcTypeOneOf(rpctype_integer, rpctype_null), "timeJump"),
            })
        )
    ),
)
"""
[i{i[normal:1,keep,timeJump,timeAbig]:type,t:timestamp,s|n:path,s|n:signal,s|n:source,?:value,i:accessLevel,s|n:userId,b|n:repeat,i:timeJump:60}]
"""
