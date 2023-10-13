"""Check that our tools for working with values are correct."""
import pytest

from shv import shvget


@pytest.mark.parametrize(
    "value,key,default,tp,expected",
    (
        (None, "foo", 3, int, 3),
        ({"foo": 42}, "foo", 3, int, 42),
        ({"foo": 42}, "foo", 3.0, float, 3.0),
        ({"foo": {"foo": 42}}, "foo", 3, int, 3),
        ({"foo": {"foo": 42}}, ("foo", "foo"), 3, int, 42),
        ({"foo": "foo"}, ("foo", "foo"), 3, int, 3),
        (42, (), 3, int, 3),
        ("foo", (), 3, int, 3),
    ),
)
def test_shvget(value, key, default, tp, expected):
    """Check implementation of shvget."""
    assert shvget(value, key, tp, default) == expected
