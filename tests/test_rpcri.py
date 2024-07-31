"""Check our implementation of fnmatch."""

import pytest

from shv import (
    rpcri_legacy_subscription,
    rpcri_match,
    rpcri_relative_to,
)


@pytest.mark.parametrize(
    "ri,path,method,signal,result",
    (
        (":ls", "", "ls", None, True),
        (":ls", "some", "ls", None, False),
        (":ls", "", "ls", "lsmod", False),
        (":ls:lsmod", "", "ls", "lsmod", True),
        (":*:*", "", "ls", "lsmod", True),
        (":*:*", "", "ls", None, False),
        (":*:lsmod", "", "ls", "lsmod", True),
        (":ls:*", "", "ls", "lsmod", True),
        ("*:ls", "foo", "ls", None, True),
        ("*/*/foo:ls", "one/two/foo", "ls", None, True),
        ("**:ls", "foo", "ls", None, True),
        ("**:ls", "foo/bar/boo", "ls", None, True),
        ("**/boo:ls", "foo/bar/boo", "ls", None, True),
        ("**/bar/**:ls", "foo/bar/boo", "ls", None, True),
        ("**/**/**:ls", "foo/bar/boo", "ls", None, True),
        ("*:ls:lsmod", "foo/faa", "ls", "lsmod", False),
        ("*/*/foo:ls", "one/two/three", "ls", None, False),
        ("**/**:ls", "foo", "ls", None, False),
        ("**/bar:ls", "foo/bar/boo", "ls", None, False),
        ("**/boo/**:ls", "foo/bar/boo", "ls", None, False),
        ("", "", "ls", None, False),
    ),
)
def test_rpcri_match(ri, path, method, signal, result):
    assert rpcri_match(ri, path, method, signal) is result


# @pytest.mark.parametrize(
#    "pattern,path,result",
#    (
#        ("", "", None),
#        ("test/some", "test", "some"),
#        ("test/some", "test/some", None),
#        ("*/*", "foo", "*"),
#        ("*/*", "foo/faa", None),
#        ("**", "foo", "**"),
#        ("foo/**", "foo", "**"),
#        ("some/**", "foo", None),
#        ("foo/**", "foo/bar", "**"),
#        ("foo/**/some", "foo/bar", "**/some"),
#        ("**/some", "foo/bar", "**/some"),
#    ),
# )
# def test_tail_pattern(pattern, path, result):
#    assert shvpath_tail(path, pattern) == result


@pytest.mark.parametrize(
    "ri,path,res",
    (
        ("**:*:*", "", "**:*:*"),
        # ("test/some:*:*chng", "", "test/some:*:*chng"),
        ("test/some:*", "test", "some:*"),
        # ("test/some:*", "test/", "some:*"),
        ("test/some:*", "test/some", None),
        ("test/some:*", "test/some/", None),
        ("test/some:*", "test/som", None),
        ("test/some/*:*", "test/some", "*:*"),
        ("test/some/*:*", "test", "some/*:*"),
        ("test/some/*:*", "tes", None),
        ("test/some/*:*", "test/some/node", None),
        ("**/some/*:*", "test/it/some", "*:*"),
        ("**/some/*:*", "test/it", "**/some/*:*"),
    ),
)
def test_relative_to(ri, path, res):
    assert rpcri_relative_to(ri, path) == res


@pytest.mark.parametrize(
    "ri,shv",
    (
        ("**:*:*", {"method": "", "path": ""}),
        ("test/this:*:*", {"method": "", "paths": "test/this"}),
        ("**:get:*chng", {"path": "", "source": "get", "methods": "*chng"}),
        ("test/this/**:*:*", {"path": "test/this", "method": ""}),
        ("test/this/*:*:*", {"paths": "test/this/*", "method": ""}),
        ("**:*:*chng", {"path": "", "methods": "*chng"}),
    ),
)
def test_to_legacy_subscription(ri, shv):
    assert rpcri_legacy_subscription(ri) == shv


def test_to_legacy_subscription_meth():
    with pytest.raises(ValueError):
        rpcri_legacy_subscription("test/**:*")
