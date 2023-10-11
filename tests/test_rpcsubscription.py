"""Check our implementation of fnmatch."""
import pytest

from shv.rpcsubscription import path_match, tail_pattern


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
