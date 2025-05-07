"""The definition of standard SHV types."""

from __future__ import annotations

import typing

from .. import SHVType
from .any import rpctype_any
from .base import RpcType
from .bitfield import RpcTypeBitfield
from .blob import rpctype_blob
from .bool import rpctype_bool
from .datetime import rpctype_datetime
from .enum import RpcTypeEnum
from .integer import RpcTypeInteger, rpctype_integer
from .list import RpcTypeList
from .map import RpcTypeMap, rpctype_map
from .oneof import RpcTypeOptional
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
            RpcTypeOptional(
                RpcTypeBitfield(
                    (1, rpctype_bool, "isGetter"),
                    (2, rpctype_bool, "isSetter"),
                    (3, rpctype_bool, "largeResult"),
                    (4, rpctype_bool, "notIndempotent"),
                    (5, rpctype_bool, "userIDRequired"),
                    (6, rpctype_bool, "isUpdatable"),
                )
            ),
            "flags",
        ),
        3: (RpcTypeOptional(rpctype_string), "paramType"),
        4: (RpcTypeOptional(rpctype_string), "resultType"),
        5: (RpcTypeInteger(0, 63), "accessLevel"),
        6: (RpcTypeMap(RpcTypeOptional(rpctype_string)), "signals"),
        63: (rpctype_map, "extra"),
    }),
)
"""
i{s:name:1,u[b:isGetter:1,b:isSetter,b:largeResult,b:notIndempotent,b:userIDRequired,b:isUpdatable]|n:flags,s|n:paramType,s|n:resultType,i(0,63):accessLevel,{s|n}:signals,{?}:extra:63}
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
        2: (RpcTypeOptional(rpctype_string), "userName"),
        3: (RpcTypeOptional(rpctype_string), "mountPoint"),
        4: (
            RpcTypeOptional(RpcTypeMap(RpcTypeOptional(rpctype_integer))),
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
        3: (RpcTypeOptional(rpctype_datetime), "accessTime"),
        4: (RpcTypeOptional(rpctype_datetime), "modTime"),
        5: (RpcTypeOptional(rpctype_integer), "maxWrite"),
    }),
)
"""
i{i:type,i:size,i:pageSize,t|n:accessTime,t|n:modTime,i|n:maxWrite}
"""

rpctype_exchange_p = RpcTypeStandard(
    "exchangeP",
    RpcTypeStruct({
        0: (rpctype_unsigned, "counter"),
        1: (RpcTypeOptional(rpctype_unsigned), "readyToReceive"),
        3: (RpcTypeOptional(rpctype_blob), "data"),
    }),
)
"""
i{u:counter,u|n:readyToReceive,b|n:data:3}
"""

rpctype_exchange_r = RpcTypeStandard(
    "exchangeR",
    RpcTypeStruct({
        1: (RpcTypeOptional(rpctype_unsigned), "readyToReceive"),
        2: (RpcTypeOptional(rpctype_unsigned), "readyToSend"),
        3: (RpcTypeOptional(rpctype_blob), "data"),
    }),
)
"""
i{u|n:readyToReceive:1,u|n:readyToSend,b|n:data}
"""

rpctype_exchange_v = RpcTypeStandard(
    "exchangeV",
    RpcTypeStruct({
        1: (RpcTypeOptional(rpctype_unsigned), "readyToReceive"),
        2: (RpcTypeOptional(rpctype_unsigned), "readyToSend"),
    }),
)
"""
i{u|n:readyToReceive:1,u|n:readyToSend}
"""

rpctype_getlog_p = RpcTypeStandard(
    "getLogP",
    RpcTypeStruct({
        1: (RpcTypeOptional(rpctype_datetime), "since"),
        2: (RpcTypeOptional(rpctype_datetime), "until"),
        3: (RpcTypeOptional(RpcTypeInteger(0)), "count"),
        4: (RpcTypeOptional(rpctype_string), "ri"),
    }),
)
"""
i{t|n:since:1,t|n:until,i(0,)|n:count,s|n:ri}
"""

rpctype_getlog_r = RpcTypeStandard(
    "getLogR",
    RpcTypeList(
        RpcTypeStruct({
            1: (RpcTypeOptional(rpctype_datetime), "timestamp"),
            2: (RpcTypeOptional(RpcTypeInteger(0)), "ref"),
            3: (RpcTypeOptional(rpctype_string), "path"),
            4: (RpcTypeOptional(rpctype_string), "signal"),
            5: (RpcTypeOptional(rpctype_string), "source"),
            6: (rpctype_any, "value"),
            7: (RpcTypeOptional(rpctype_string), "userId"),
            8: (RpcTypeOptional(rpctype_bool), "repeat"),
        })
    ),
)
"""
[i{t|n:timestamp:1,i(0,)|n:ref,s|n:path,s|n:signal,s|n:source,?:value,s|n:userId,b|n:repeat}]
"""


rpctype_history_records = RpcTypeStandard(
    "historyRecords",
    RpcTypeList(
        RpcTypeStruct({
            0: (
                RpcTypeEnum({1: "normal", 2: "keep", 3: "timeJump", 4: "timeAbig"}),
                "type",
            ),
            1: (rpctype_datetime, "timestamp"),
            2: (RpcTypeOptional(rpctype_string), "path"),
            3: (RpcTypeOptional(rpctype_string), "signal"),
            4: (RpcTypeOptional(rpctype_string), "source"),
            5: (rpctype_any, "value"),
            6: (RpcTypeInteger(0, 63), "accessLevel"),
            7: (RpcTypeOptional(rpctype_string), "userId"),
            8: (RpcTypeOptional(rpctype_bool), "repeat"),
            60: (RpcTypeOptional(rpctype_integer), "timeJump"),
        })
    ),
)
"""
[i{i[normal:1,keep,timeJump,timeAbig]:type,t:timestamp,s|n:path,s|n:signal,s|n:source,?:value,i:accessLevel,s|n:userId,b|n:repeat,i:timeJump:60}]
"""
