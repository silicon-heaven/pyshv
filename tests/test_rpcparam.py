"""Check that our tools for working with values are correct."""

import pytest

from shv import SHVGetKey, shvarg, shvget


@pytest.mark.parametrize(
    "value,key,default,expected",
    (
        (None, "foo", 3, 3),
        ({"foo": 42}, "foo", 3, 42),
        ({}, "foo", 3.0, 3.0),
        ({"foo": {"foo": 42}}, ("foo", "foo"), 3, 42),
        ({"bar": "foo"}, ("foo", "foo"), 3, 3),
        ({"foo": {"bar": 33}}, (SHVGetKey("foo", 2), SHVGetKey("bar", 3)), 3, 33),
        ({2: {3: 33}}, (SHVGetKey("foo", 2), SHVGetKey("bar", 3)), 3, 33),
        (None, (), 3, 3),
        (42, (), 3, 42),
    ),
)
def test_shvget(value, key, default, expected):
    """Check implementation of shvget."""
    assert shvget(value, key, default) == expected


@pytest.mark.parametrize(
    "value,index,default,expected",
    (
        (None, 0, 3, 3),
        (41, 1, 4, 4),
        (41, 0, 4, 41),
        ([41, 42, 43], 1, 3, 42),
        ([41, None, 43], 1, 3, 3),
        ([], 0, 3, 3),
        ([41], 1, 3, 3),
        ([41], 0, 3, 41),
        ("foo", 1, None, None),
        ("foo", 0, 4, "foo"),
    ),
)
def test_shvarg(value, index, default, expected):
    """Check implementation of shvarg."""
    assert shvarg(value, index, default) == expected
