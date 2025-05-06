"""Check that we can serialize and deserialize Cpon."""

import datetime
import decimal

import pytest

from shv import (
    CponReader,
    CponWriter,
    SHVIMap,
    SHVInt,
    SHVMap,
    SHVMeta,
    SHVUInt,
    shvmeta,
)

DATA: list = [
    ("null", None),
    (b"null", None),
    ("true", True),
    ("false", False),
    ("0", 0),
    ("-1", -1),
    ("-2", -2),
    ("7", 7),
    ("42", 42),
    ("1u", SHVUInt(1)),
    (f"{2**31 - 1}u", SHVUInt(2**31 - 1)),
    (f"{2**32 - 1}u", SHVUInt(2**32 - 1)),
    (str(2**31 - 1), 2**31 - 1),
    (str(2**32 - 1), 2**32 - 1),
    (str(2**53 - 1), 2**53 - 1),
    (str(1 - 2**53), 1 - 2**53),
    ("0x1.bep+7", 223.0),
    ("-0x1.cp+0", -1.75),
    ("2.3", decimal.Decimal((0, (2, 3), -1))),
    ("-0.00012", decimal.Decimal((1, (1, 2), -5))),
    ("3E+2", decimal.Decimal((0, (3,), 2))),
    ('""', ""),
    ('"foo"', "foo"),
    ('"dvaačtyřicet"', "dvaačtyřicet"),
    ('"some\\t\\"tab\\""', 'some\t"tab"'),
    ("[]", []),
    ("[1]", [1]),
    ("[1,2,3]", [1, 2, 3]),
    ("[[]]", [[]]),
    ('{"foo":"bar"}', {"foo": "bar"}),
    ("i{1:2}", {1: 2}),
    ('[1u,{"a":1},2.3]', [SHVUInt(1), {"a": 1}, decimal.Decimal("2.3")]),
    ("<1:2>3", SHVMeta.new(3, {1: 2})),
    ("[1,<7:8>9]", [1, SHVMeta.new(9, {7: 8})]),
    (
        '<8:3u>i{2:[[".broker",<1:2>true]]}',
        SHVMeta.new({2: [[".broker", SHVMeta.new(True, {1: 2})]]}, {8: SHVUInt(3)}),
    ),
    (
        '<1:2,"foo":<5:6>"bar">[1u,{"a":1},2.3]',
        SHVMeta.new(
            [SHVUInt(1), {"a": 1}, decimal.Decimal("2.3")],
            {1: 2, "foo": SHVMeta.new("bar", {5: 6})},
        ),
    ),
    ("<1:2>[3,<4:5>6]", SHVMeta.new([3, SHVMeta.new(6, {4: 5})], {1: 2})),
    (
        '<4:"svete">i{2:<4:"svete">[0,1]}',
        SHVMeta.new({2: SHVMeta.new([0, 1], {4: "svete"})}, {4: "svete"}),
    ),
    ('b"ab\\cd\\t\\r\\n"', b"ab\xcd\t\r\n"),
    (
        'd"2018-02-02T00:00:00Z"',
        datetime.datetime(2018, 2, 2, tzinfo=datetime.UTC),
    ),
    (
        'd"2027-05-03T11:30:12.345+01"',
        datetime.datetime(
            2027,
            5,
            3,
            11,
            30,
            12,
            345000,
            tzinfo=datetime.timezone(datetime.timedelta(hours=1)),
        ),
    ),
]


@pytest.mark.parametrize(
    "cpon,data",
    [
        *DATA,
        ("0x42", 0x42),
        ("2.0p+0", 2.0),
        ("2p0", 2.0),
        ("2.5P+1", 5.0),
        ("-2.0p-1", -1.0),
        ("1.5p-2", 0.375),
        ("223.", decimal.Decimal("223.0")),
        ("2.30", decimal.Decimal("2.3")),
        ("-1234567890.", decimal.Decimal((1, (1, 2, 3, 4, 5, 6, 7, 8, 9), 1))),
        ("[1, 2, 3]", [1, 2, 3]),
        ("<>1", SHVInt(1)),
        (
            'd"2017-05-03T18:30:00Z"',
            datetime.datetime(2017, 5, 3, 18, 30, tzinfo=datetime.UTC),
        ),
        (
            'd"2017-05-03T22:30:00+04"',
            datetime.datetime(
                2017,
                5,
                3,
                22,
                30,
                tzinfo=datetime.timezone(datetime.timedelta(seconds=14400)),
            ),
        ),
        (
            'd"2017-05-03T11:30:00-0700"',
            datetime.datetime(
                2017,
                5,
                3,
                11,
                30,
                tzinfo=datetime.timezone(datetime.timedelta(seconds=-25200)),
            ),
        ),
        (
            'd"2017-05-03T15:00:00-0330"',
            datetime.datetime(
                2017,
                5,
                3,
                15,
                tzinfo=datetime.timezone(datetime.timedelta(seconds=-12600)),
            ),
        ),
    ],
)
def test_reader(cpon, data):
    res = CponReader.unpack(cpon)
    assert res == data
    assert type(res) is type(data)
    assert shvmeta(res) == shvmeta(data)


def test_reader_uint():
    assert isinstance(CponReader.unpack("1u"), SHVUInt)


@pytest.mark.parametrize(
    "cpon,data",
    [
        *DATA,
        ("1", SHVMeta.new(1, {})),
        ("1.0", decimal.Decimal((0, (1,), 0))),
    ],
)
def test_writer(cpon, data):
    res = CponWriter.pack(data)
    if isinstance(cpon, str):
        res = res.decode("utf-8")
    assert res == cpon


@pytest.mark.parametrize(
    "cpon,res",
    (
        ("0xab", b"171"),
        ("-0xCD", b"-205"),
        ("0x1a2b3c4d", b"439041101"),
        ("12.3e-10", b"1.23E-9"),
        ("-0.00012", b"-0.00012"),
        ("-1234567890.", b"-1234567890.0"),
        ("[1,]", b"[1]"),
        ('i{\n\t1: "bar",\n\t345u : "foo",\n}', b'i{1:"bar",345:"foo"}'),
        ('<"foo":"bar",1:2>i{1:<7:8>9}', b'<1:2,"foo":"bar">i{1:<7:8>9}'),
        ("i{1:2 // comment to end of line\n}", b"i{1:2}"),
        ('d"2019-05-03T11:30:00-0700"', b'd"2019-05-03T11:30:00-07"'),
        ('x"abcd"', b'b"\\ab\\cd"'),
        (
            "/*comment 1*/{ /*comment 2*/\n"
            + '\t"foo"/*comment "3"*/: "bar", //comment to end of line\n'
            + '\t"baz" : 1,\n'
            + "/*\n"
            + "\tmultiline comment\n"
            + '\t"baz" : 1,\n'
            + '\t"baz" : 1, // single inside multi\n'
            + "*/\n"
            + "}",
            b'{"baz":1,"foo":"bar"}',
        ),
    ),
)
def test_style(cpon, res):
    data = CponReader.unpack(cpon)
    assert CponWriter.pack(data) == res


def test_unpack_empty_map_imap():
    assert isinstance(
        CponReader.unpack(CponWriter.pack(SHVMeta.new(SHVIMap()))), SHVIMap
    )
    assert isinstance(CponReader.unpack(CponWriter.pack(SHVMeta.new(SHVMap()))), SHVMap)
