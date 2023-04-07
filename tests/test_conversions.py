"""Check that conversions are performed correctly."""
import pytest

from chainpack.chainpack import ChainPackReader, ChainPackWriter
from chainpack.cpon import CponReader, CponWriter


@pytest.mark.parametrize(
    "cpon",
    (
        str((2**31 - 1)).encode() + b"u",
        str(2**32 - 1).encode() + b"u",
        "" + str(2**31 - 1),
        "" + str(-(2**30 - 1)),
        "" + str(2**53 - 1),
        "" + str(-(2**53 - 1)),
        str(2**32 - 1).encode(),
        "true",
        "false",
        "null",
        "1u",
        "134",
        "7",
        "-2",
        "223.",
        "2.30",
        '"foo"',
        '""',
        "[]",
        "[1]",
        "[1,2,3]",
        "[[]]",
        '{"foo":"bar"}',
        "i{1:2}",
        '[1u,{"a":1},2.30]',
        "<1:2>3",
        "[1,<7:8>9]",
        "<>1",
        '<8:3u>i{2:[[".broker",<1:2>true]]}',
        '<1:2,"foo":<5:6>"bar">[1u,{"a":1},2.30]',
        "<1:2>[3,<4:5>6]",
        '<4:"svete">i{2:<4:"svete">[0,1]}',
        'b"ab\\cd\\t\\r\\n"',
        'd"2018-02-02T00:00:00Z"',
        'd"2027-05-03T11:30:12.345+01"',
    ),
)
def tests_one_to_one(cpon):
    rv1 = CponReader.unpack(cpon)
    cpk1 = ChainPackWriter.pack(rv1)
    rv2 = ChainPackReader.unpack(cpk1)
    cpn2 = CponWriter.pack(rv2)
    if isinstance(cpon, str):
        cpon = cpon.encode()
    if isinstance(cpn2, str):
        cpn2 = cpn2.encode()
    assert cpon == cpn2


@pytest.mark.parametrize(
    "cpon,res",
    (
        ("0xab", b"171"),
        ("-0xCD", b"-205"),
        ("0x1a2b3c4d", b"439041101"),
        ("12.3e-10", b"123e-11"),
        ("-0.00012", b"-12e-5"),
        ("-1234567890.", b"-1234567890."),
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
def test_convert(cpon, res):
    rv1 = CponReader.unpack(cpon)
    cpk1 = ChainPackWriter.pack(rv1)
    rv2 = ChainPackReader.unpack(cpk1)
    cpn2 = CponWriter.pack(rv2)
    assert cpn2 == res


@pytest.mark.parametrize("date", (
    'd"2017-05-03T18:30:00Z"',
    'd"2017-05-03T22:30:00+04"',
    'd"2017-05-03T11:30:00-0700"',
    'd"2017-05-03T15:00:00-0330"',
))
def test_datetime(date):
    val = CponReader.unpack(date)
    assert val.value.epochMsec == 1493836200000
