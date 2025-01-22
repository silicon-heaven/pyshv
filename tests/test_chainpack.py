"""Check that we can serialize and deserialize Chainpack."""

import datetime
import decimal

import pytest

from shv import (
    ChainPackReader,
    ChainPackWriter,
    SHVIMap,
    SHVMap,
    SHVMeta,
    SHVUInt,
    shvmeta,
)

# You can get chainpack using this shell command:
#   echo 'null' | cp2cp --ip --oc \
#     | python -c "import sys; print(repr(sys.stdin.buffer.read()))"
DATA: list = [
    (b"\x80", None),
    (b"\xfe", True),
    (b"\xfd", False),
    (b"@", 0),
    (b"\x82A", -1),
    (b"\x82B", -2),
    (b"G", 7),
    (b"j", 42),
    (b"\x01", SHVUInt(1)),
    (b"\x81\xf0\x7f\xff\xff\xff", SHVUInt(2**31 - 1)),
    (b"\x81\xf0\xff\xff\xff\xff", SHVUInt(2**32 - 1)),
    (b"\x81\xf4\x80\x00\x00\x00\x00\x00\x00\x00", SHVUInt(1 << 63)),
    (b"\x82\xf0\x7f\xff\xff\xff", 2**31 - 1),
    (b"\x82\xf1\x00\xff\xff\xff\xff", 2**32 - 1),
    (b"\x82\xf3\x1f\xff\xff\xff\xff\xff\xff", 2**53 - 1),
    (b"\x82\xf3\x9f\xff\xff\xff\xff\xff\xff", 1 - 2**53),
    (b"\x83\x00\x00\x00\x00\x00\xe0k@", 223.0),
    (b"\x8c\x17A", decimal.Decimal((0, (2, 3), -1))),
    (b"\x86\x00", ""),
    (b"\x86\x03foo", "foo"),
    (b"\x88\xff", []),
    (b"\x88A\xff", [1]),
    (b"\x88ABC\xff", [1, 2, 3]),
    (b"\x88\x88\xff\xff", [[]]),
    (b"\x89\x86\x03foo\x86\x03bar\xff", {"foo": "bar"}),
    (b"\x8aAB\xff", {1: 2}),
    (
        b"\x88\x01\x89\x86\x01aA\xff\x8c\x17A\xff",
        [SHVUInt(1), {"a": 1}, decimal.Decimal("2.3")],
    ),
    (b"\x8bAB\xffC", SHVMeta.new(3, {1: 2})),
    (b"\x88A\x8bGH\xffI\xff", [1, SHVMeta.new(9, {7: 8})]),
    (
        b"\x8bH\x03\xff\x8aB\x88\x88\x86\x07.broker\x8bAB\xff\xfe\xff\xff\xff",
        SHVMeta.new({2: [[".broker", SHVMeta.new(True, {1: 2})]]}, {8: SHVUInt(3)}),
    ),
    (
        b"\x8bAB\x86\x03foo\x8bEF\xff\x86\x03bar\xff\x88\x01\x89\x86\x01aA\xff\x8c\x17A\xff",
        SHVMeta.new(
            [SHVUInt(1), {"a": 1}, decimal.Decimal("2.3")],
            {1: 2, "foo": SHVMeta.new("bar", {5: 6})},
        ),
    ),
    (
        b"\x8bAB\xff\x88C\x8bDE\xffF\xff",
        SHVMeta.new([3, SHVMeta.new(6, {4: 5})], {1: 2}),
    ),
    (
        b"\x8bD\x86\x05svete\xff\x8aB\x8bD\x86\x05svete\xff\x88@A\xff\xff",
        SHVMeta.new({2: SHVMeta.new([0, 1], {4: "svete"})}, {4: "svete"}),
    ),
    (b"\x85\x00", b""),
    (b"\x85\x06ab\xcd\t\r\n", b"ab\xcd\t\r\n"),
    (
        b"\x8d\x04",
        datetime.datetime(2018, 2, 2, 0, 0, 0, 1000, tzinfo=datetime.UTC),
    ),
    (
        b"\x8d\x82\x11",
        datetime.datetime(
            2018,
            2,
            2,
            1,
            0,
            0,
            1000,
            tzinfo=datetime.timezone(datetime.timedelta(hours=1)),
        ),
    ),
]


@pytest.mark.parametrize(
    "chainpack,data",
    [
        *DATA,
        (b"\x8efoo\x00", "foo"),
    ],
)
def test_reader(chainpack, data):
    obj = ChainPackReader.unpack(chainpack)
    assert obj == data
    assert shvmeta(obj) == shvmeta(data)


def test_reader_uint():
    assert isinstance(ChainPackReader.unpack(b"\x01"), SHVUInt)


@pytest.mark.parametrize(
    "chainpack,data",
    [
        *DATA,
        (b"A", SHVMeta.new(1)),
    ],
)
def test_writer(chainpack, data):
    res = ChainPackWriter.pack(data)
    assert res == chainpack


def test_writer_cstring():
    obj = ChainPackWriter()
    obj.write_cstring("foo")
    assert obj.stream.getvalue() == b"\x8efoo\x00"


def test_unpack_empty_map_imap():
    assert isinstance(
        ChainPackReader.unpack(ChainPackWriter.pack(SHVMeta.new(SHVIMap()))), SHVIMap
    )
    assert isinstance(
        ChainPackReader.unpack(ChainPackWriter.pack(SHVMeta.new(SHVMap()))), SHVMap
    )
