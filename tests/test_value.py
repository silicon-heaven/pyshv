"""Check our meta value assignment."""

import datetime
import decimal

import pytest

from shv import (
    SHVBool,
    SHVBytes,
    SHVDatetime,
    SHVDecimal,
    SHVFloat,
    SHVIMap,
    SHVInt,
    SHVList,
    SHVMap,
    SHVMeta,
    SHVNull,
    SHVStr,
    SHVUInt,
    is_shvbool,
    is_shvnull,
    is_shvtype,
    shvmeta_eq,
)

CLASSES: list = [
    (SHVNull, []),
    (SHVBool, [True]),
    (SHVInt, []),
    (SHVUInt, []),
    (SHVFloat, []),
    (SHVBytes, []),
    (SHVStr, []),
    (SHVDatetime, [2020, 1, 2, 3]),
    (SHVDecimal, []),
    (SHVList, []),
    (SHVMap, []),
    (SHVIMap, []),
]


@pytest.mark.parametrize("cls,args", CLASSES)
def test_meta(cls, args):
    """Test our SHVMeta based classes."""
    obj = cls(*args)
    assert obj.meta == {}
    meta = {"foo": 42}
    obj.meta.update(meta)
    assert obj.meta == meta


def test_null():
    """Check that we simulate None somewhat closely."""
    null = SHVNull()
    assert bool(null) == bool(None)
    assert hash(null) == hash(None)


def test_bool():
    """Check that we can compare booleans."""
    false = False
    true = True
    assert SHVBool(True)
    assert not SHVBool(False)
    assert SHVBool(True) == true
    assert SHVBool(True) != false
    assert SHVBool(False) == false
    assert SHVBool(False) != true
    assert SHVBool(True) == SHVBool(True)
    assert SHVBool(False) == SHVBool(False)
    assert SHVBool(False) != SHVBool(True)
    assert SHVBool(True) != SHVBool(False)


REPRS: tuple = (
    (SHVBool, True, False),
    (SHVInt, 1, 42),
    (SHVFloat, 1.0, 4.2),
    (SHVBytes, b"foo", b""),
    (SHVStr, "foo", ""),
    (SHVDecimal, decimal.Decimal("4.2e12"), decimal.Decimal()),
    (SHVList, [1, "foo"], []),
    (SHVMap, {"foo": 1, "": 42}, {}),
    (SHVIMap, {1: "foo", 42: ""}, {}),
)


@pytest.mark.parametrize("cls,value1,value2", REPRS)
def test_repr(cls, value1, value2):
    """Check representation interchange."""
    obj1 = cls(value1)
    obj2 = cls(value2)
    assert obj1 == value1
    assert obj2 == value2
    obj1 = value2
    assert obj1 == obj2


@pytest.mark.parametrize("cls,value1,value2", REPRS)
def test_noteq(cls, value1, value2):
    """Check representation interchange in not equal."""
    obj1 = cls(value1)
    obj2 = cls(value2)
    assert obj2 != value1
    assert obj1 != value2
    assert obj1 != obj2


@pytest.mark.parametrize("cls,value1,value2", REPRS)
def test_hash(cls, value1, value2):
    """Our objects should not modify hash and thus it has to be the same."""
    if cls in {SHVList, SHVMap, SHVIMap}:
        return  # Unhashable types
    assert hash(cls(value1)) == hash(value1)
    assert hash(cls(value2)) == hash(value2)


def test_datetime():
    timestamp = 45322
    shv = SHVDatetime.fromtimestamp(45322)
    base = datetime.datetime.fromtimestamp(timestamp)
    assert shv == base
    assert shv.year == 1970


@pytest.mark.parametrize(
    "value,expected",
    (
        (None, SHVNull()),
        (True, SHVBool(True)),
        (False, SHVBool(False)),
        (42, SHVInt(42)),
        (4.2, SHVFloat(4.2)),
        (b"foo", SHVBytes(b"foo")),
        ("foo", SHVStr("foo")),
        (datetime.datetime.fromtimestamp(352434), SHVDatetime.fromtimestamp(352434)),
        (decimal.Decimal(42), SHVDecimal(42)),
        ([1, "foo"], SHVList([1, "foo"])),
        ({"foo": 1}, SHVMap({"foo": 1})),
        ({1: "foo"}, SHVIMap({1: "foo"})),
    ),
)
def test_new(value, expected):
    obj = SHVMeta.new(value, {})
    assert obj == value
    assert value == obj
    assert obj == expected


@pytest.mark.parametrize(
    "value,expected",
    (
        (None, True),
        (SHVNull(), True),
        (0, False),
    ),
)
def test_is_shvnull(value, expected):
    assert is_shvnull(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    (
        (True, True),
        (False, True),
        (SHVBool(True), True),
        (SHVBool(False), True),
        (0, False),
    ),
)
def test_is_shvbool(value, expected):
    assert is_shvbool(value) is expected


@pytest.mark.parametrize(
    "value,expected",
    (
        (None, True),
        (SHVNull(), True),
        (True, True),
        (False, True),
        (SHVBool(True), True),
        (SHVBool(False), True),
        (42, True),
        (0.42, True),
        (decimal.Decimal("0.42"), True),
        (b"foo", True),
        ("foo", True),
        (datetime.datetime.now(), True),
        ([4, 2], True),
        (["foo", datetime.datetime.now(), None, False], True),
        ({10: 4, 1: 2}, True),
        ({"tenth": 4, "cent": 2}, True),
        ({10: 4, "cent": 2}, False),
        ([{10: 4, 1: [2, 0]}, {"tenth": 4, "cent": 2}], True),
        (datetime.UTC, False),
    ),
)
def test_is_shvtype(value, expected):
    assert is_shvtype(value) is expected


@pytest.mark.parametrize("cls,args", CLASSES)
def test_meta_eq(cls, args):
    """meta_eq should compare metas to each other."""
    obj1 = cls(*args)
    obj2 = cls(*args)
    assert shvmeta_eq(obj1, obj2)
    meta = {"foo": 42}
    obj1.meta.update(meta)
    assert not shvmeta_eq(obj1, obj2)
    obj2.meta.update(meta)
    assert shvmeta_eq(obj1, obj2)


@pytest.mark.parametrize(
    "obj1,obj2",
    (
        (SHVInt(42), 42),
        (SHVNull(), None),
        (SHVNull(), SHVNull()),
    ),
)
def test_meta_eq_eq(obj1, obj2):
    assert shvmeta_eq(obj1, obj2)


@pytest.mark.parametrize("obj1,obj2", ((SHVInt(42), SHVUInt(42)),))
def test_meta_eq_ne(obj1, obj2):
    assert not shvmeta_eq(obj1, obj2)
