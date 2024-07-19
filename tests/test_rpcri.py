"""Check our implementation of fnmatch."""

import pytest

from shv.rpcri import RpcRI, path_match, tail_pattern
from shv.value import SHVType


@pytest.mark.parametrize(
    "pattern,path",
    (
        ("", ""),
        ("*", "foo"),
        ("*/*/foo", "one/two/foo"),
        ("**", "foo"),
        ("**", "foo/bar/boo"),
        ("**/boo", "foo/bar/boo"),
        ("**/bar/**", "foo/bar/boo"),
        ("**/**/**", "foo/bar/boo"),
    ),
)
def test_path_match(pattern, path):
    assert path_match(path, pattern)


@pytest.mark.parametrize(
    "pattern,path",
    (
        ("", "some"),
        ("*", "foo/faa"),
        ("*/*/foo", "one/two/three"),
        ("**/**", "foo"),
        ("**/bar", "foo/bar/boo"),
        ("**/boo/**", "foo/bar/boo"),
    ),
)
def test_path_match_invalid(pattern, path):
    assert not path_match(path, pattern)


@pytest.mark.parametrize(
    "pattern,path,result",
    (
        ("", "", None),
        ("test/some", "test", "some"),
        ("test/some", "test/some", None),
        ("*/*", "foo", "*"),
        ("*/*", "foo/faa", None),
        ("**", "foo", "**"),
        ("foo/**", "foo", "**"),
        ("some/**", "foo", None),
        ("foo/**", "foo/bar", "**"),
        ("foo/**/some", "foo/bar", "**/some"),
        ("**/some", "foo/bar", "**/some"),
    ),
)
def test_tail_pattern(pattern, path, result):
    assert tail_pattern(path, pattern) == result


text_ri = (
    ("", RpcRI(path="")),
    ("**", RpcRI()),
    ("test:set", RpcRI(path="test", method="set")),
    (
        "test/**:switch:*chng",
        RpcRI(path="test/**", method="switch", signal="*chng"),
    ),
)


@pytest.mark.parametrize(
    "text,res",
    (
        *text_ri,
        ("**:*:*", RpcRI()),
        ("**::*", RpcRI(method="get")),
        ("::*", RpcRI(path="", method="get")),
        ("test/**::*chng", RpcRI(path="test/**", method="get", signal="*chng")),
    ),
)
def test_parse(text, res):
    assert RpcRI.parse(text) == res


@pytest.mark.parametrize(
    "res,ri",
    (
        *text_ri,
        ("**:get", RpcRI(method="get")),
        (":get", RpcRI(path="", method="get")),
    ),
)
def test_str(ri, res):
    assert str(ri) == res


@pytest.mark.parametrize(
    "sub,path,res",
    (
        (RpcRI(), "", RpcRI()),
        (RpcRI("test/some"), "", RpcRI("test/some")),
        (RpcRI("test/some"), "test", RpcRI("some")),
        (RpcRI("test/some"), "test/", RpcRI("some")),
        (RpcRI("test/some"), "test/some", None),
        (RpcRI("test/some"), "test/some/", None),
        (RpcRI("test/some"), "test/som", None),
        (RpcRI("test/some/*"), "test/some", RpcRI("*")),
        (RpcRI("test/some/*"), "test", RpcRI("some/*")),
        (RpcRI("test/some/*"), "tes", None),
        (RpcRI("test/some/*"), "test/some/node", None),
        (RpcRI("**/some/*"), "test/it/some", RpcRI("*")),
        (RpcRI("**/some/*"), "test/it", RpcRI("**/some/*")),
    ),
)
def test_relative_to(sub, path, res):
    assert sub.relative_to(path) == res


DATA: list[tuple[RpcRI, int | None, SHVType]] = [
    (RpcRI(), None, {}),
    (RpcRI("test/this"), None, {"paths": "test/this"}),
    (RpcRI(), 42, {"ttl": 42}),
    (RpcRI("**", "get", "*chng"), None, {"source": "get", "signal": "*chng"}),
]


@pytest.mark.parametrize("obj,ttl,shv", DATA)
def test_to_shv(shv, ttl, obj):
    assert obj.to_subscription(ttl) == shv


@pytest.mark.parametrize(
    "obj,ttl,shv",
    [
        *DATA,
        (RpcRI("test/this/**"), None, {"path": "test/this"}),
    ],
)
def test_from_shv(shv, ttl, obj):
    assert RpcRI.from_subscription(shv) == (obj, ttl)


@pytest.mark.parametrize(
    "shv,msg",
    (
        ({"ttl": "invalid"}, "Invalid type"),
        ({"paths": 22}, "Invalid type"),
        ([], "Expected Map"),
    ),
)
def test_from_shv_invalid(shv, msg):
    with pytest.raises(ValueError, match=msg):
        RpcRI.from_subscription(shv)


@pytest.mark.parametrize(
    "obj,ttl,shv",
    (
        (RpcRI("test/this/**"), None, {"path": "test/this", "method": ""}),
        (RpcRI(), None, {"path": "", "method": ""}),
        (RpcRI("test/this/*"), None, {"paths": "test/this/*", "method": ""}),
        (RpcRI(signal="*chng"), None, {"path": "", "methods": "*chng"}),
    ),
)
def test_to_shv_compatible(shv, ttl, obj):
    assert obj.to_subscription(ttl, True) == shv
