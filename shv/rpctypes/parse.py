"""Parse the SHV RPC type string."""

from __future__ import annotations

import decimal
import re

from .any import RpcTypeAny
from .base import RpcType
from .bitfield import RpcTypeBitfield
from .blob import RpcTypeBlob
from .bool import rpctype_bool
from .datetime import RpcTypeDateTime
from .decimal import RpcTypeDecimal
from .double import RpcTypeDouble
from .enum import RpcTypeEnum
from .imap import RpcTypeIMap
from .integer import RpcTypeInteger
from .keystruct import RpcTypeKeyStruct
from .list import RpcTypeList
from .map import RpcTypeMap
from .null import rpctype_null
from .oneof import RpcTypeOneOf
from .standard import (
    rpctype_alert,
    rpctype_clientinfo,
    rpctype_dir,
    rpctype_exchange_p,
    rpctype_exchange_r,
    rpctype_exchange_v,
    rpctype_getlog_p,
    rpctype_getlog_r,
    rpctype_history_records,
    rpctype_stat,
)
from .string import RpcTypeString
from .struct import RpcTypeStruct
from .tuple import RpcTypeTuple
from .unsigned import RpcTypeUnsigned

_decimal_re = re.compile(r"-?(?:0|(?:[1-9][0-9]*))?(?:\.[0-9]+)?")


def rpctype_parse(rpctype: str) -> RpcType:
    """Parse the given value as RPC Type string.

    :param rpctype: The string representation of the RPC type hint.
    :return: The object representation.
    :raises RpcTypeParseError: In case type hint has invalid format.
    """
    i = 0

    def hasc(expected: str, whitelist: bool = True) -> str | None:
        nonlocal i
        if len(rpctype) > i and (
            expected is None or ((rpctype[i] in expected) is whitelist)
        ):
            i += 1
            return rpctype[i - 1]
        return None

    def check(expected: str) -> None:
        nonlocal i
        if not rpctype.startswith(expected, i):
            raise RpcTypeParseError(f"Expected '{expected}' at {i}")
        i += len(expected)

    def _parse_int() -> int:
        value = 0
        while c := hasc("123456789" + ("0" if value else "")):
            value = value * 10 + ord(c) - ord("0")
        return value

    def parse_number(positive: bool = False) -> int | None:
        if hasc("0"):
            return 0
        positive = positive or not hasc("-")
        mod = hasc("^>")
        value = _parse_int()
        return (
            (2**value if mod == "^" else 2**value - 1 if mod == ">" else value)
            * (1 if positive else -1)
            if value
            else None
        )

    def parse_number_required(positive: bool = False) -> int:
        previ = i
        if (res := parse_number(positive)) is not None:
            return res
        raise RpcTypeParseError(f"Expected number at {previ}")

    def parse_decimal_number() -> decimal.Decimal | None:
        nonlocal i
        match = _decimal_re.match(rpctype[i:])
        if not match or not match.group(0):
            return None
        endi = i + len(match.group(0))
        result = decimal.Decimal(rpctype[i:endi])
        i = endi
        return result

    def parse_text() -> str:
        return "".join(iter(lambda: hasc("[]{}():,|", False), None))

    def parse_text_required() -> str:
        if result := parse_text():
            return result
        raise RpcTypeParseError(f"Text expected at {i}")

    def parse_integer() -> RpcTypeInteger:
        imin, imax = None, None
        if hasc("("):
            imin = parse_number()
            check(",")
            imax = parse_number()
            check(")")
        return RpcTypeInteger(imin, imax, parse_text())

    def parse_unsigned() -> RpcTypeUnsigned:
        imin, imax = None, None
        if hasc("("):
            imax = parse_number(True)
            if hasc(","):
                imin = imax
                imax = parse_number(True)
            check(")")
        return RpcTypeUnsigned(imin or 0, imax, parse_text())

    def parse_decimal() -> RpcTypeDecimal:
        dmin, dmax, dpres = None, None, None
        if hasc("("):
            dmin = parse_decimal_number()
            check(",")
            dmax = parse_decimal_number()
            if hasc(","):
                dpres = parse_number()
            check(")")
        return RpcTypeDecimal(dmin, dmax, dpres, parse_text())

    def parse_enum() -> RpcTypeEnum:
        items = {}
        index = 0
        while True:
            key = parse_text_required()
            if hasc(":"):
                index = parse_number_required()
            if index in items:
                raise RpcTypeParseError(f"Reuse of the integer key {index}")
            items[index] = key
            index += 1
            if hasc("]"):
                break
            check(",")
        return RpcTypeEnum(items)

    def parse_size() -> tuple[int, int | None]:
        imin, imax = None, None
        if hasc("("):
            imin = parse_number(True)
            imax = parse_number(True) if hasc(",") else imin
            check(")")
        return imin or 0, imax

    def parse_list_tuple() -> RpcTypeList | RpcTypeTuple:
        tp = parse()
        if hasc("]"):  # List
            return RpcTypeList(tp, *parse_size())
        # Tuple
        ivalues = []
        while True:
            check(":")
            ivalues.append((tp, parse_text_required()))
            if not hasc(","):
                break
            tp = parse()
        check("]")
        return RpcTypeTuple(*ivalues)

    def parse_imap_struct() -> RpcTypeIMap | RpcTypeStruct:
        tp = parse()
        if hasc("}"):  # IMap
            return RpcTypeIMap(tp)
        # Struct
        values = {}
        index = 0
        while True:
            check(":")
            key = parse_text_required()
            if hasc(":"):
                index = parse_number_required()
            if index in values:
                raise RpcTypeParseError(f"Reuse of the integer key {index}")
            values[index] = (tp, key)
            index += 1
            if hasc("}"):
                break
            check(",")
            tp = parse()
        return RpcTypeStruct(values)

    def parse_map_keystruct() -> RpcTypeMap | RpcTypeKeyStruct:
        tp = parse()
        if hasc("}"):  # Map
            return RpcTypeMap(tp)
        # KeyStruct
        mvalues = {}
        while True:
            check(":")
            key = parse_text_required()
            if key in mvalues:
                raise RpcTypeParseError(f"Reuse of the key '{key}'")
            mvalues[key] = tp
            if hasc("}"):
                break
            check(",")
            tp = parse()
        return RpcTypeKeyStruct(mvalues)

    def parse_bitfield() -> RpcTypeBitfield:
        bitems = []
        ikey = 0
        while True:
            tp = parse()
            tpsiz = RpcTypeBitfield.bitsize(tp)
            check(":")
            key = parse_text_required()
            if hasc(":"):
                ikey = parse_number_required()
            bitems.append((ikey, tp, key))
            ikey += tpsiz or 0
            if hasc("]"):
                break
            check(",")
        return RpcTypeBitfield(*bitems)

    def parse() -> RpcType:
        res: RpcType | None = None
        match hasc("nbiufdsxt[{!?"):
            case "n":  # Null
                res = rpctype_null
            case "b":  # Bool
                res = rpctype_bool
            case "i":
                match hasc("[{"):
                    case "[":  # Enum
                        res = parse_enum()
                    case "{":  # IMap or Struct
                        res = parse_imap_struct()
                    case _:  # Integer
                        res = parse_integer()
            case "u":
                match hasc("["):
                    case "[":  # Bitfield
                        res = parse_bitfield()
                    case _:  # Unsigned integer
                        res = parse_unsigned()
            case "f":  # Double (floating point number)
                res = RpcTypeDouble(parse_text())
            case "d":  # Decimal
                res = parse_decimal()
            case "s":  # String
                res = RpcTypeString(*parse_size())
            case "x":  # Blob
                res = RpcTypeBlob(*parse_size())
            case "t":  # DateTime
                res = RpcTypeDateTime()
            case "[":  # List or Tuple
                res = parse_list_tuple()
            case "{":
                res = parse_map_keystruct()
            case "!":  # Standard types
                match parse_text_required():
                    case "dir":
                        res = rpctype_dir
                    case "alert":
                        res = rpctype_alert
                    case "clientInfo":
                        res = rpctype_clientinfo
                    case "stat":
                        res = rpctype_stat
                    case "exchangeP":
                        res = rpctype_exchange_p
                    case "exchangeR":
                        res = rpctype_exchange_r
                    case "exchangeV":
                        res = rpctype_exchange_v
                    case "getLogP":
                        res = rpctype_getlog_p
                    case "getLogR":
                        res = rpctype_getlog_r
                    case "historyRecords":
                        res = rpctype_history_records
                    case tpname:
                        raise RpcTypeParseError(f"Invalid standard type '{tpname}'")
            case "?":
                name = ""
                if hasc("("):
                    name = parse_text()
                    check(")")
                res = RpcTypeAny(name)
        if res is None:
            raise RpcTypeParseError(
                f"Invalid character '{rpctype[i]}' at {i}"
                if len(rpctype) > i
                else f"Missing character at {i}"
            )
        if hasc("|"):
            res = RpcTypeOneOf(res, parse())
        return res

    try:
        result = parse()
    except ValueError as exc:
        raise RpcTypeParseError(*exc.args) from exc
    if i != len(rpctype):
        raise RpcTypeParseError(f"Unexpected character '{rpctype[i]}' at {i}")
    return result


class RpcTypeParseError(ValueError):
    """The RPC Type parse error."""
