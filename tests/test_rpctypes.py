"""Check the RPC Types abstraction."""

import datetime
import decimal
import re

import pytest

from shv import SHVUInt
from shv.rpctypes import (
    RpcTypeAny,
    RpcTypeBitfield,
    RpcTypeBlob,
    RpcTypeBool,
    RpcTypeDateTime,
    RpcTypeDecimal,
    RpcTypeDouble,
    RpcTypeEnum,
    RpcTypeIMap,
    RpcTypeInteger,
    RpcTypeKeyStruct,
    RpcTypeList,
    RpcTypeMap,
    RpcTypeNull,
    RpcTypeOneOf,
    RpcTypeOptional,
    RpcTypeParseError,
    RpcTypeString,
    RpcTypeStruct,
    RpcTypeTuple,
    RpcTypeTupleItem,
    RpcTypeUnsigned,
    rpctype_alert,
    rpctype_any,
    rpctype_blob,
    rpctype_bool,
    rpctype_clientinfo,
    rpctype_datetime,
    rpctype_decimal,
    rpctype_dir,
    rpctype_double,
    rpctype_exchange_p,
    rpctype_exchange_r,
    rpctype_exchange_v,
    rpctype_get,
    rpctype_getlog_p,
    rpctype_getlog_r,
    rpctype_history_records,
    rpctype_imap,
    rpctype_integer,
    rpctype_list,
    rpctype_map,
    rpctype_null,
    rpctype_parse,
    rpctype_stat,
    rpctype_string,
    rpctype_unsigned,
)

DATA = [
    ("n", rpctype_null),
    ("b", rpctype_bool),
    ("i", RpcTypeInteger()),
    ("ikG", RpcTypeInteger(unit="kG")),
    ("i(-2,2)", RpcTypeInteger(-2, 2)),
    ("i(,2)", RpcTypeInteger(None, 2)),
    ("i(-2,)%", RpcTypeInteger(-2, None, "%")),
    ("i(^7,>8)", RpcTypeInteger(128, 255)),
    ("u", RpcTypeUnsigned()),
    ("uK", RpcTypeUnsigned(unit="K")),
    ("u(2)", RpcTypeUnsigned(0, 2)),
    ("u(1,10)", RpcTypeUnsigned(1, 10)),
    ("u(125,)%", RpcTypeUnsigned(125, None, "%")),
    ("u(^7,>8)", RpcTypeUnsigned(128, 255)),
    ("i[FALSE,TRUE]", RpcTypeEnum({0: "FALSE", 1: "TRUE"})),
    ("i[fail:-1,success]", RpcTypeEnum({-1: "fail", 0: "success"})),
    ("f", RpcTypeDouble()),
    ("fkG", RpcTypeDouble("kG")),
    ("d", RpcTypeDecimal()),
    ("d(-.3,.8)", RpcTypeDecimal(decimal.Decimal("-0.3"), decimal.Decimal("0.8"))),
    (
        "d(0,100,2)%",
        RpcTypeDecimal(decimal.Decimal("0"), decimal.Decimal("100"), 2, "%"),
    ),
    ("d(,,-2)", RpcTypeDecimal(None, None, -2)),
    ("s", RpcTypeString()),
    ("s(16)", RpcTypeString(16, 16)),
    ("s(,63)", RpcTypeString(0, 63)),
    ("x", RpcTypeBlob()),
    ("x(16)", RpcTypeBlob(16, 16)),
    ("x(,63)", RpcTypeBlob(0, 63)),
    ("t", rpctype_datetime),
    ("[i(0,100)]", RpcTypeList(RpcTypeInteger(0, 100))),
    ("[?](8)", RpcTypeList(rpctype_any, 8, 8)),
    ("[?](1,4)", RpcTypeList(rpctype_any, 1, 4)),
    ("[?](8,)", RpcTypeList(rpctype_any, 8)),
    ("[?](,4)", RpcTypeList(rpctype_any, 0, 4)),
    ("[d:x,d:y]", RpcTypeTuple((RpcTypeDecimal(), "x"), (RpcTypeDecimal(), "y"))),
    ("i{?}", RpcTypeIMap(rpctype_any)),
    ("i{i(3,9)}", RpcTypeIMap(RpcTypeInteger(3, 9))),
    (
        "i{t:date,i(0,63):level,s:id,?:info}",
        RpcTypeStruct({
            0: (rpctype_datetime, "date"),
            1: (RpcTypeInteger(0, 63), "level"),
            2: (rpctype_string, "id"),
            3: (rpctype_any, "info"),
        }),
    ),
    (
        "i{s:name:1,t:birth}",
        RpcTypeStruct({1: (rpctype_string, "name"), 2: (rpctype_datetime, "birth")}),
    ),
    ("{?}", RpcTypeMap(rpctype_any)),
    ("{i(0,2)}", RpcTypeMap(RpcTypeInteger(0, 2))),
    (
        "{s:name,t:birth}",
        RpcTypeKeyStruct({"name": rpctype_string, "birth": rpctype_datetime}),
    ),
    (
        "u[b:bool,u(3):umax:4,u(2,3):ushift,i[one,two]:enum]",
        RpcTypeBitfield(
            (0, rpctype_bool, "bool"),
            (4, RpcTypeUnsigned(0, 3), "umax"),
            (6, RpcTypeUnsigned(2, 3), "ushift"),
            (7, RpcTypeEnum({0: "one", 1: "two"}), "enum"),
        ),
    ),
    ("?", rpctype_any),
    ("?(Some type)", RpcTypeAny("Some type")),
    ("i|n", RpcTypeOneOf(rpctype_integer, rpctype_null)),
    ("i|s|d", RpcTypeOneOf(rpctype_integer, rpctype_string, rpctype_decimal)),
    ("!dir", rpctype_dir),
    ("!get", rpctype_get),
    ("!alert", rpctype_alert),
    ("!clientInfo", rpctype_clientinfo),
    ("!stat", rpctype_stat),
    ("!exchangeP", rpctype_exchange_p),
    ("!exchangeR", rpctype_exchange_r),
    ("!exchangeV", rpctype_exchange_v),
    ("!getLogP", rpctype_getlog_p),
    ("!getLogR", rpctype_getlog_r),
    ("!historyRecords", rpctype_history_records),
]


@pytest.mark.parametrize(
    "text,obj",
    (
        *DATA,
        ("i(,)", RpcTypeInteger()),
        ("i(0,)", RpcTypeInteger(0)),
        ("u(,2)", RpcTypeUnsigned(0, 2)),
        ("u(,0)", RpcTypeUnsigned(0, 0)),
    ),
)
def test_text2obj(text, obj):
    """Check that text can be converted to the object and is equal."""
    assert rpctype_parse(text) == obj


@pytest.mark.parametrize("text,obj", DATA)
def test_obj2text(text, obj):
    """Check that object can be converted to the object and is the same."""
    assert str(obj) == text


@pytest.mark.parametrize(
    "text,errmsg",
    (
        ("", "Missing character at 0"),
        ("i(", "Expected ',' at 2"),
        ("i[val:text]", "Expected number at 6"),
        ("i[:1]", "Text expected at 2"),
        ("u[i:item]", "Type 'i' not supported in Bitfield"),
        ("u[u(4,):item]", "Type 'u(4,)' not supported in Bitfield"),
        ("u[u(7):one,u(3):two:2]", "Bit 2 is used in multiple items"),
        ("i[again,again]", "Duplicates are not allowed in enum"),
        ("i[zero,again:0]", "Reuse of the integer key 0"),
        ("[i]Nothing", "Unexpected character 'N' at 3"),
        ("i{i:same,i:same}", "Duplicate keys are not allowed"),
        ("i{i:one,i:two:0}", "Reuse of the integer key 0"),
        ("{i:same,i:same}", "Reuse of the key 'same'"),
        ("[s](2,1)", "Minimum is greater than maximum"),
        ("s(2,1)", "Minimum is greater than maximum"),
        ("x(2,1)", "Minimum is greater than maximum"),
        ("d(2,1)", "Minimum is greater than maximum"),
        ("i(2,1)", "Minimum is greater than maximum"),
        ("u(2,1)", "Minimum is greater than maximum"),
        ("!invalid", "Invalid standard type 'invalid'"),
    ),
)
def test_textfail(text, errmsg):
    """Check the error message when parsing the RPC type definition."""
    with pytest.raises(RpcTypeParseError, match=f"^{re.escape(errmsg)}$"):
        rpctype_parse(text)


@pytest.mark.parametrize(
    "obj,args,errmsg",
    (
        (RpcTypeUnsigned, [-2, 5], "Unsigned limit can't be negative number"),
        (RpcTypeString, [-1], "String size can be only positive number"),
        (RpcTypeBlob, [-1], "Blob size can be only positive number"),
        (RpcTypeList, [rpctype_integer, -1], "List size can be only positive number"),
        (RpcTypeTuple, [], "Tuple requires at least one item"),
        (RpcTypeStruct, [{}], "Struct requires at least one item"),
        (RpcTypeKeyStruct, [{}], "KeyStruct requires at least one item"),
        (
            RpcTypeBitfield,
            [(-1, rpctype_bool, "foo")],
            "Bit index can't be negative number",
        ),
        (
            RpcTypeBitfield,
            [(0, rpctype_string, "foo")],
            "Type 's' not supported in Bitfield",
        ),
    ),
)
def test_initfail(obj, args, errmsg):
    """Check the error message when initializing RPC type objects.

    There are some checks that just can't be triggered through
    ``test_textfail`` but they are present for the usage from Python directly.
    """
    with pytest.raises(ValueError, match=f"^{re.escape(errmsg)}$"):
        obj(*args)


@pytest.mark.parametrize(
    "obj,value",
    (
        (rpctype_null, None),
        (rpctype_bool, True),
        (rpctype_bool, False),
        (rpctype_integer, 42),
        (rpctype_unsigned, SHVUInt(42)),
        (rpctype_datetime, datetime.datetime.fromtimestamp(0)),
        (rpctype_decimal, decimal.Decimal("1.0")),
        (rpctype_double, 4.2),
        (rpctype_string, "foo"),
        (rpctype_blob, b"foo"),
        (rpctype_list, [42, "foo"]),
        (rpctype_map, {"foo": 42}),
        (rpctype_imap, {42: "foo"}),
        (rpctype_any, None),
        (
            RpcTypeDecimal(decimal.Decimal("0"), decimal.Decimal("100"), 2),
            decimal.Decimal("0.01"),
        ),
        (RpcTypeEnum({1: "foo", 3: "bar"}), 1),
        (
            RpcTypeTuple(
                (rpctype_bool, "one"),
                (RpcTypeOneOf(rpctype_bool, rpctype_null), "second"),
            ),
            [True],
        ),
        (
            RpcTypeTuple(
                (rpctype_bool, "one"),
                (RpcTypeOneOf(rpctype_bool, rpctype_null), "second"),
            ),
            [True, True],
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOneOf(rpctype_datetime, rpctype_null), "birth"),
            }),
            {1: "john", 2: datetime.datetime.fromtimestamp(42)},
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOneOf(rpctype_datetime, rpctype_null), "birth"),
            }),
            {1: "john"},
        ),
        (
            RpcTypeKeyStruct({
                "name": rpctype_string,
                "birth": RpcTypeOneOf(rpctype_datetime, rpctype_null),
            }),
            {"name": "john", "birth": datetime.datetime.fromtimestamp(42)},
        ),
        (
            RpcTypeKeyStruct({
                "name": rpctype_string,
                "birth": RpcTypeOneOf(rpctype_datetime, rpctype_null),
            }),
            {"name": "john"},
        ),
        (
            RpcTypeBitfield(
                (0, rpctype_bool, "bool"),
                (4, RpcTypeUnsigned(0, 3), "umax"),
                (6, RpcTypeUnsigned(2, 3), "ushift"),
                (7, RpcTypeEnum({0: "one", 1: "two"}), "enum"),
            ),
            0,
        ),
        (
            RpcTypeBitfield(
                (0, rpctype_bool, "bool"),
                (4, RpcTypeUnsigned(0, 3), "umax"),
                (6, RpcTypeUnsigned(2, 3), "ushift"),
                (7, RpcTypeEnum({0: "one", 1: "two"}), "enum"),
            ),
            1 + (2 << 4) + (1 << 6) + (1 << 7),
        ),
        (
            rpctype_alert,
            {0: datetime.datetime.fromtimestamp(44), 1: 42, 2: "TestAlert"},
        ),
    ),
)
def test_is_valid(obj, value):
    """Check validation of the valid types."""
    assert obj.is_valid(value)


@pytest.mark.parametrize(
    "obj,value,msg",
    (
        (rpctype_null, 1, "Null"),
        (rpctype_bool, None, "Bool"),
        (rpctype_integer, None, "Integer"),
        (RpcTypeInteger(0, 3), -42, "minimal value 0"),
        (RpcTypeInteger(0, 3), 42, "maximal value 3"),
        (rpctype_unsigned, None, "Unsigned Integer"),
        (rpctype_unsigned, 1, "Unsigned Integer"),
        (RpcTypeUnsigned(1, 3), SHVUInt(0), "minimal value 1"),
        (RpcTypeUnsigned(0, 3), SHVUInt(4), "maximal value 3"),
        (RpcTypeEnum({0: "one", 1: "two"}), None, "Integer(Enum)"),
        (RpcTypeEnum({0: "one", 1: "two"}), 2, "defined in Enum"),
        (rpctype_datetime, 42, "DateTime"),
        (rpctype_decimal, 42, "Decimal"),
        (rpctype_decimal, decimal.Decimal("inf"), "finite Decimal number"),
        (rpctype_decimal, decimal.Decimal("-inf"), "finite Decimal number"),
        (rpctype_decimal, decimal.Decimal("nan"), "finite Decimal number"),
        (RpcTypeDecimal("-1.0", "1.0"), decimal.Decimal("-1.01"), "minimal value -1.0"),
        (RpcTypeDecimal("-1.0", "1.0"), decimal.Decimal("1.01"), "maximal value 1.0"),
        (
            RpcTypeDecimal("-1.0", "1.0", 1),
            decimal.Decimal("0.51"),
            "maximum precision is 1",
        ),
        (rpctype_double, None, "Double"),
        (rpctype_string, b"foo", "String"),
        (RpcTypeString(1, 3), "fooo", "at most 3 characters"),
        (RpcTypeString(1, 3), "", "at least 1 characters"),
        (rpctype_blob, "foo", "Blob"),
        (RpcTypeBlob(1, 3), b"fooo", "at most 3 bytes"),
        (RpcTypeBlob(1, 3), b"", "at least 1 bytes"),
        (rpctype_list, 42, "List"),
        (RpcTypeList(rpctype_integer, 2, 2), [1], "2 number of List items"),
        (RpcTypeList(rpctype_integer, 1, 3), [], "at least 1 List items"),
        (
            RpcTypeList(rpctype_integer, 1, 3),
            [1, 2, 3, 4],
            "at most 3 List items",
        ),
        (
            RpcTypeList(rpctype_integer, 2, 2),
            [0, 1.0],
            "List item 1: Integer",
        ),
        (
            RpcTypeTuple((rpctype_integer, "x"), (rpctype_integer, "y")),
            None,
            "Tuple(List)",
        ),
        (
            RpcTypeTuple((rpctype_integer, "x"), (rpctype_integer, "y")),
            [0, 0, 0],
            "at most 2 items",
        ),
        (
            RpcTypeTuple((rpctype_integer, "x"), (rpctype_integer, "y")),
            [0, None],
            "Tuple item y: Integer",
        ),
        (rpctype_imap, {"foo": 42}, "IMap"),
        (
            RpcTypeIMap(rpctype_integer),
            {42: "foo"},
            "IMap item 42: Integer",
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOneOf(rpctype_datetime, rpctype_null), "birth"),
            }),
            {"foo": 42},
            "Struct(IMap)",
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOneOf(rpctype_datetime, rpctype_null), "birth"),
            }),
            {3: "foo", 4: 42},
            "defined Struct keys: 3, 4",
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOptional(rpctype_datetime), "birth"),
            }),
            {1: 42},
            "Struct item 1: String",
        ),
        (rpctype_map, {42: "foo"}, "Map"),
        (
            RpcTypeMap(rpctype_integer),
            {"foo": "foo"},
            "Map item foo: Integer",
        ),
        (
            RpcTypeKeyStruct({
                "name": rpctype_string,
                "birth": RpcTypeOptional(rpctype_datetime),
            }),
            {1: 42},
            "KeyStruct(Map)",
        ),
        (
            RpcTypeKeyStruct({
                "name": rpctype_string,
                "birth": RpcTypeOptional(rpctype_datetime),
            }),
            {"invalid": 42, "second": "foo"},
            "defined KeyStruct keys: second, invalid",
        ),
        (
            RpcTypeKeyStruct({
                "name": rpctype_string,
                "birth": RpcTypeOptional(rpctype_datetime),
            }),
            {"name": 42},
            "KeyStruct item name: String",
        ),
        (
            RpcTypeBitfield(
                (0, rpctype_bool, "bool"),
                (4, RpcTypeUnsigned(0, 3), "umax"),
                (6, RpcTypeUnsigned(2, 3), "ushift"),
                (7, RpcTypeEnum({0: "one", 1: "two"}), "enum"),
            ),
            None,
            "Bitfield(Int)",
        ),
        (
            RpcTypeBitfield(
                (0, rpctype_bool, "bool"),
                (4, RpcTypeUnsigned(0, 3), "umax"),
                (6, RpcTypeUnsigned(2, 3), "ushift"),
                (7, RpcTypeEnum({0: "one", 1: "two"}), "enum"),
            ),
            2,
            "unused bits in Bitfield to be zero: 0b10",
        ),
        (
            RpcTypeBitfield(
                (0, rpctype_bool, "bool"),
                (2, RpcTypeEnum({0: "zero", 2: "two"}), "enum"),
            ),
            5,
            "Bitfield item enum: defined in Enum",
        ),
        (RpcTypeOneOf(rpctype_bool, rpctype_null), 42, "Bool | Null"),
    ),
)
def test_validate(obj, value, msg):
    """Check validation of the invalid types."""
    assert obj.validate(value) == msg


INFLATE_DATA = [
    (rpctype_null, None, None),
    (rpctype_bool, True, True),
    (rpctype_bool, False, False),
    (rpctype_integer, 42, 42),
    (RpcTypeEnum({1: "one", 2: "two"}), 1, "one"),
    (RpcTypeEnum({1: "one", 2: "two"}), 2, "two"),
    (rpctype_double, 1.0, 1.0),
    (rpctype_decimal, decimal.Decimal("1.0"), decimal.Decimal("1.0")),
    (rpctype_string, "foo", "foo"),
    (
        rpctype_datetime,
        datetime.datetime.fromtimestamp(42),
        datetime.datetime.fromtimestamp(42),
    ),
    (RpcTypeList(RpcTypeEnum({1: "foo", 2: "bar"})), [1, 2, 1], ["foo", "bar", "foo"]),
    (
        RpcTypeTuple((rpctype_integer, "x"), (rpctype_integer, "y")),
        [42, 24],
        {"x": 42, "y": 24},
    ),
    (
        RpcTypeTuple(
            (rpctype_string, "name"), (RpcTypeOptional(rpctype_datetime), "birth")
        ),
        ["foo"],
        {"name": "foo", "birth": None},
    ),
    (
        RpcTypeIMap(RpcTypeEnum({1: "foo", 2: "bar"})),
        {1: 1, 2: 2, 3: 1},
        {1: "foo", 2: "bar", 3: "foo"},
    ),
    (
        RpcTypeStruct({
            1: (rpctype_string, "name"),
            2: (RpcTypeOptional(rpctype_datetime), "birth"),
        }),
        {1: "foo", 2: datetime.datetime.fromtimestamp(42)},
        {"name": "foo", "birth": datetime.datetime.fromtimestamp(42)},
    ),
    (
        RpcTypeStruct({
            1: (rpctype_string, "name"),
            2: (RpcTypeOptional(rpctype_datetime), "birth"),
        }),
        {1: "foo"},
        {"name": "foo"},
    ),
    (
        RpcTypeMap(RpcTypeEnum({1: "foo", 2: "bar"})),
        {"one": 1, "two": 2, "three": 1},
        {"one": "foo", "two": "bar", "three": "foo"},
    ),
    (
        RpcTypeKeyStruct({
            "type": RpcTypeEnum({1: "regular", 2: "device"}),
            "path": rpctype_string,
            "extra": RpcTypeOptional(rpctype_string),
        }),
        {"type": 1, "path": "/null"},
        {"type": "regular", "path": "/null"},
    ),
    (
        RpcTypeBitfield(
            (0, rpctype_bool, "bool"),
            (4, RpcTypeUnsigned(0, 3), "umax"),
            (6, RpcTypeUnsigned(2, 3), "ushift"),
            (7, RpcTypeEnum({0: "one", 1: "two"}), "enum"),
        ),
        0,
        {"bool": False, "umax": SHVUInt(0), "ushift": SHVUInt(2), "enum": "one"},
    ),
    (
        RpcTypeBitfield(
            (0, rpctype_bool, "bool"),
            (4, RpcTypeUnsigned(0, 3), "umax"),
            (6, RpcTypeUnsigned(2, 3), "ushift"),
            (7, RpcTypeEnum({0: "one", 1: "two"}), "enum"),
        ),
        0xF1,
        {"bool": True, "umax": SHVUInt(3), "ushift": SHVUInt(3), "enum": "two"},
    ),
]


@pytest.mark.parametrize("obj,deflated,inflated", INFLATE_DATA)
def test_inflate(obj, deflated, inflated):
    """Check that inflate provides expected result."""
    assert obj.inflate(deflated) == inflated


@pytest.mark.parametrize("obj,deflated,inflated", INFLATE_DATA)
def test_deflate(obj, deflated, inflated):
    """Check that deflate provides expected result."""
    assert obj.deflate(inflated) == deflated


@pytest.mark.parametrize(
    "obj,val,errmsg",
    (
        (RpcTypeEnum({1: "one", 2: "two"}), 3, "defined in Enum"),
        (RpcTypeEnum({1: "one", 2: "two"}), "three", "Integer(Enum)"),
        (RpcTypeList(RpcTypeEnum({1: "foo", 2: "bar"})), None, "List"),
        (
            RpcTypeList(RpcTypeEnum({1: "foo", 2: "bar"})),
            [None],
            "List item 0: Integer(Enum)",
        ),
        (
            RpcTypeTuple((rpctype_integer, "x"), (rpctype_integer, "y")),
            {"x": 42, "y": 24},
            "Tuple(List)",
        ),
        (
            RpcTypeTuple((rpctype_integer, "x"), (rpctype_integer, "y")),
            [42, None],
            "Tuple item 1: Integer",
        ),
        (RpcTypeIMap(RpcTypeEnum({1: "foo", 2: "bar"})), {"foo": 1}, "IMap"),
        (
            RpcTypeIMap(RpcTypeEnum({1: "foo", 2: "bar"})),
            {1: None},
            "IMap item 1: Integer(Enum)",
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOptional(rpctype_datetime), "birth"),
            }),
            {"foo": 1},
            "Struct(IMap)",
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOptional(rpctype_datetime), "birth"),
            }),
            {1: "foo", 3: 42, 4: None},
            "defined Struct keys: 3, 4",
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOptional(rpctype_datetime), "birth"),
            }),
            {1: "foo", 2: 42},
            "Struct item 2: DateTime | Null",
        ),
        (RpcTypeMap(RpcTypeEnum({1: "foo", 2: "bar"})), {1: "foo"}, "Map"),
        (
            RpcTypeMap(RpcTypeEnum({1: "foo", 2: "bar"})),
            {"foo": None},
            "Map item foo: Integer(Enum)",
        ),
        (
            RpcTypeKeyStruct({
                "type": RpcTypeEnum({1: "regular", 2: "device"}),
                "path": rpctype_string,
            }),
            {1: "some"},
            "KeyStruct(Map)",
        ),
        (
            RpcTypeKeyStruct({
                "type": RpcTypeEnum({1: "regular", 2: "device"}),
                "path": rpctype_string,
            }),
            {"type": 1, "path": "/", "other": "some"},
            "defined KeyStruct keys: other",
        ),
        (
            RpcTypeKeyStruct({
                "type": RpcTypeEnum({1: "regular", 2: "device"}),
                "path": rpctype_string,
            }),
            {"type": 3, "path": "/"},
            "KeyStruct item type: defined in Enum",
        ),
        (
            RpcTypeBitfield(
                (0, rpctype_bool, "bool"),
                (4, RpcTypeUnsigned(0, 3), "umax"),
                (6, RpcTypeUnsigned(2, 3), "ushift"),
                (7, RpcTypeEnum({0: "one", 1: "two"}), "enum"),
            ),
            None,
            "Bitfield(Int)",
        ),
        (
            RpcTypeBitfield(
                (0, rpctype_bool, "bool"),
                (4, RpcTypeUnsigned(0, 3), "umax"),
                (6, RpcTypeUnsigned(2, 3), "ushift"),
                (7, RpcTypeEnum({0: "one", 1: "two"}), "enum"),
            ),
            2,
            "unused bits in Bitfield to be zero: 0b10",
        ),
        (
            RpcTypeBitfield((0, RpcTypeUnsigned(0, 5), "uval")),
            7,
            "Bitfield item 0: maximal value 5",
        ),
    ),
)
def test_inflate_invalid(obj, val, errmsg):
    with pytest.raises(ValueError, match=f"^{re.escape(errmsg)}$"):
        obj.inflate(val)


@pytest.mark.parametrize(
    "obj,val,errmsg",
    (
        (RpcTypeEnum({1: "one", 2: "two"}), "three", "defined in Enum"),
        (RpcTypeEnum({1: "one", 2: "two"}), 2, "String(Enum)"),
        (RpcTypeList(RpcTypeEnum({1: "foo", 2: "bar"})), None, "List"),
        (
            RpcTypeList(RpcTypeEnum({1: "foo", 2: "bar"})),
            [1],
            "List item 0: String(Enum)",
        ),
        (
            RpcTypeTuple((rpctype_integer, "x"), (rpctype_integer, "y")),
            [42, 24],
            "Map(Tuple)",
        ),
        (
            RpcTypeTuple((rpctype_integer, "x"), (rpctype_integer, "y")),
            {"x": 42, "y": 24, "z": 12, "q": None},
            "defined Tuple keys: q, z",
        ),
        (
            RpcTypeTuple((rpctype_integer, "x"), (rpctype_integer, "y")),
            {"x": 42, "y": None},
            "Tuple item 1: Integer",
        ),
        (
            RpcTypeIMap(RpcTypeEnum({1: "foo", 2: "bar"})),
            {"foo": None},
            "IMap",
        ),
        (
            RpcTypeIMap(RpcTypeEnum({1: "foo", 2: "bar"})),
            {1: 3},
            "IMap item 1: String(Enum)",
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOptional(rpctype_datetime), "birth"),
            }),
            {1: "foo"},
            "Map(Struct)",
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOptional(rpctype_datetime), "birth"),
            }),
            {"name": "foo", "invalid": None},
            "defined Struct keys: invalid",
        ),
        (
            RpcTypeStruct({
                1: (rpctype_string, "name"),
                2: (RpcTypeOptional(rpctype_datetime), "birth"),
            }),
            {"name": "foo", "birth": 42},
            "Struct item 2: DateTime | Null",
        ),
        (
            RpcTypeMap(RpcTypeEnum({1: "foo", 2: "bar"})),
            {1: None},
            "Map",
        ),
        (
            RpcTypeMap(RpcTypeEnum({1: "foo", 2: "bar"})),
            {"foo": 3},
            "Map item foo: String(Enum)",
        ),
        (
            RpcTypeKeyStruct({
                "type": RpcTypeEnum({1: "regular", 2: "device"}),
                "path": rpctype_string,
            }),
            {1: "foo"},
            "KeyStruct(Map)",
        ),
        (
            RpcTypeKeyStruct({
                "type": RpcTypeEnum({1: "regular", 2: "device"}),
                "path": rpctype_string,
            }),
            {"type": 1, "path": "/", "other": None},
            "defined KeyStruct keys: other",
        ),
        (
            RpcTypeKeyStruct({
                "type": RpcTypeEnum({1: "regular", 2: "device"}),
                "path": rpctype_string,
            }),
            {"type": "regular", "path": 42},
            "KeyStruct item path: String",
        ),
        (
            RpcTypeBitfield((0, rpctype_bool, "bool")),
            {1: "foo"},
            "Map(Bitfield)",
        ),
        (
            RpcTypeBitfield((0, rpctype_bool, "bool")),
            {"bool": False, "invalid": None},
            "defined Bitfield keys: invalid",
        ),
        (
            RpcTypeBitfield(
                (0, rpctype_bool, "bool"),
                (1, RpcTypeUnsigned(0, 3), "umax"),
            ),
            {"bool": False},
            "Bitfield item 1",
        ),
        (
            RpcTypeBitfield((0, RpcTypeUnsigned(0, 3), "umax")),
            {"umax": 42},
            "Bitfield item 0: Unsigned Integer",
        ),
    ),
)
def test_deflate_invalid(obj, val, errmsg):
    with pytest.raises(ValueError, match=f"^{re.escape(errmsg)}$"):
        obj.deflate(val)


@pytest.mark.parametrize(
    "obj1,obj2",
    (
        (rpctype_null, RpcTypeNull()),
        (rpctype_bool, RpcTypeBool()),
        (rpctype_integer, RpcTypeInteger()),
        (rpctype_unsigned, RpcTypeUnsigned()),
        (rpctype_datetime, RpcTypeDateTime()),
        (rpctype_double, RpcTypeDouble()),
        (rpctype_decimal, RpcTypeDecimal()),
        (rpctype_string, RpcTypeString()),
        (rpctype_blob, RpcTypeBlob()),
        (rpctype_list, RpcTypeList()),
        (rpctype_map, RpcTypeMap()),
        (rpctype_imap, RpcTypeIMap()),
    ),
)
def test_singletons(obj1, obj2):
    assert obj1 is obj2


def test_integer_attr():
    assert rpctype_integer.minimum is None
    assert rpctype_integer.maximum is None
    assert not rpctype_integer.unit
    with pytest.raises(ValueError, match=r"^Unit contains forbidden characters$"):
        RpcTypeInteger(unit="]")


def test_unsigned_attr():
    assert rpctype_unsigned.minimum == 0
    assert rpctype_unsigned.maximum is None
    assert not rpctype_unsigned.unit
    with pytest.raises(ValueError, match=r"^Unit contains forbidden characters$"):
        RpcTypeUnsigned(unit="]")


def test_decimal_attr():
    assert rpctype_decimal.minimum is None
    assert rpctype_decimal.maximum is None
    assert rpctype_decimal.precision is None
    assert not rpctype_decimal.unit
    with pytest.raises(ValueError, match=r"^Unit contains forbidden characters$"):
        RpcTypeDecimal(unit="]")


def test_double_attr():
    assert not rpctype_double.unit
    with pytest.raises(ValueError, match=r"^Unit contains forbidden characters$"):
        RpcTypeDouble(unit="]")


def test_string_attr():
    assert rpctype_string.minlen == 0
    assert rpctype_string.maxlen is None


def test_blob_attr():
    assert rpctype_blob.minlen == 0
    assert rpctype_blob.maxlen is None


def test_list_attr():
    assert rpctype_list.type is rpctype_any
    assert rpctype_list.minlen == 0
    assert rpctype_list.maxlen is None


def test_map_attr():
    assert rpctype_map.type is rpctype_any


def test_imap_attr():
    assert rpctype_imap.type is rpctype_any


def test_enum_attr():
    tp = RpcTypeEnum({1: "foo", 3: "bar"})
    assert len(tp) == 2


def test_tuple_attr():
    tp = RpcTypeTuple(
        (rpctype_bool, "one"), (RpcTypeOneOf(rpctype_bool, rpctype_null), "second")
    )
    assert len(tp) == 2
    assert tp[0] == RpcTypeTupleItem(rpctype_bool, "one")
    assert tp[0:2] == [
        RpcTypeTupleItem(rpctype_bool, "one"),
        RpcTypeTupleItem(RpcTypeOneOf(rpctype_bool, rpctype_null), "second"),
    ]


def test_struct_attr():
    tp = RpcTypeStruct({1: (rpctype_string, "name"), 2: (rpctype_datetime, "birth")})
    assert len(tp) == 2
    assert tp[1] == (rpctype_string, "name")
    assert tp.key("name") == 1
    assert tp.key("birth") == 2
    with pytest.raises(KeyError):
        tp.key("invalid")
    assert list(tp) == [1, 2]


def test_keystruct_attr():
    tp = RpcTypeKeyStruct({"name": rpctype_string, "birth": rpctype_datetime})
    assert len(tp) == 2
    assert tp["name"] is rpctype_string
    assert list(tp) == ["name", "birth"]


def test_bitfield_attr():
    tp = RpcTypeBitfield((0, rpctype_bool, "bool"), (4, RpcTypeUnsigned(0, 3), "umax"))
    assert len(tp) == 2
    assert list(tp) == [
        (0, rpctype_bool, "bool"),
        (4, RpcTypeUnsigned(0, 3), "umax"),
    ]


@pytest.mark.parametrize(
    "tp",
    (
        rpctype_bool,
        RpcTypeEnum({0: "zero", 1: "one"}),
        RpcTypeUnsigned(0, 100),
        RpcTypeUnsigned(42, 84),
    ),
)
def test_bitfield_is_supported(tp):
    assert RpcTypeBitfield.is_supported(tp)


@pytest.mark.parametrize(
    "tp",
    (
        rpctype_integer,
        RpcTypeEnum({0: "zero", -1: "minus"}),
    ),
)
def test_bitfield_not_is_supported(tp):
    assert not RpcTypeBitfield.is_supported(tp)


def test_deposit_invalid_value():
    errmsg = "maximal value 3"
    with pytest.raises(ValueError, match=f"^{re.escape(errmsg)}$"):
        RpcTypeBitfield.deposit(SHVUInt(20), 0, RpcTypeUnsigned(0, 3))


def test_oneof_dedup():
    tp = RpcTypeOneOf(rpctype_bool, rpctype_null, rpctype_bool, rpctype_null)
    assert tp.types == (rpctype_bool, rpctype_null)


def test_any_attr():
    assert not rpctype_any.alias


@pytest.mark.parametrize(
    ("tp", "name", "text"),
    (
        (
            rpctype_dir,
            "dir",
            "i{s:name:1,u[b:isGetter:1,b:isSetter,b:largeResult,b:notIndempotent,b:userIDRequired,b:isUpdatable]|n:flags,s|n:paramType,s|n:resultType,i(0,63):accessLevel,{s|n}:signals,{?}:extra:63}",
        ),
        (rpctype_alert, "alert", "i{t:date,i(0,63):level,s:id,?:info}"),
        (
            rpctype_clientinfo,
            "clientInfo",
            "i{i:clientId:1,s|n:userName,s|n:mountPoint,{i|n}|n:subscriptions,{?}:extra:63}",
        ),
        (
            rpctype_stat,
            "stat",
            "i{i:type,i:size,i:pageSize,t|n:accessTime,t|n:modTime,i|n:maxWrite}",
        ),
        (rpctype_exchange_p, "exchangeP", "i{u:counter,u|n:readyToReceive,x|n:data:3}"),
        (
            rpctype_exchange_r,
            "exchangeR",
            "i{u|n:readyToReceive:1,u|n:readyToSend,x|n:data}",
        ),
        (rpctype_exchange_v, "exchangeV", "i{u|n:readyToReceive:1,u|n:readyToSend}"),
        (
            rpctype_getlog_p,
            "getLogP",
            "i{t|n:since:1,t|n:until,i(0,)|n:count,s|n:ri}",
        ),
        (
            rpctype_getlog_r,
            "getLogR",
            "[i{t|n:timestamp:1,i(0,)|n:ref,s|n:path,s|n:signal,s|n:source,?:value,s|n:userId,b|n:repeat}]",
        ),
        (
            rpctype_history_records,
            "historyRecords",
            "[i{i[normal:1,keep,timeJump,timeAbig]:type,t:timestamp,s|n:path,s|n:signal,s|n:source,?:value,i(0,63):accessLevel,s|n:userId,b|n:repeat,i|n:timeJump:60}]",
        ),
    ),
)
def test_standard_repr(tp, name, text):
    """Compare standard types against representation in standard."""
    assert tp.name == name
    assert str(tp) == f"!{name}"
    assert str(tp.type) == text
