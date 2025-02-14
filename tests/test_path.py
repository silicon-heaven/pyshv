"""Check the SHV path correctness."""

import os

import pytest

from shv import SHVPath


def test_nospace():
    with pytest.raises(ValueError):
        _ = SHVPath("some", "with path")


@pytest.mark.parametrize(
    "path,expected",
    (
        (SHVPath(), tuple()),
        (SHVPath("/some"), ("some",)),
        (SHVPath("/some/extra/node"), ("some", "extra", "node")),
    ),
)
def test_parts(path, expected):
    assert path.parts == expected


@pytest.mark.parametrize(
    "path,expected",
    (
        (SHVPath(), ""),
        (SHVPath("/some"), "some"),
        (SHVPath("/some", ".."), ""),
        (SHVPath("", ".."), ""),
        (SHVPath("some", ""), "some"),
        (SHVPath("some/node", "/from/root"), "from/root"),
    ),
)
def test_str(path, expected):
    assert str(path) == expected


def test_osfspath():
    assert os.fspath(SHVPath("test/node")) == "test/node"


def test_repr():
    assert repr(SHVPath("test/node")) == "SHVPath('test/node')"


@pytest.mark.parametrize(
    "path,expected",
    ((SHVPath(), False), (SHVPath("node"), True)),
)
def test_bool(path, expected):
    assert bool(path) is expected


def test_strpath():
    assert (SHVPath("some") / "node") == "some/node"


def test_pathstr():
    assert ("some" / SHVPath("node")) == SHVPath("some/node")


def test_hash():
    path = SHVPath()
    dct = {path: True, SHVPath("some/node"): False}
    assert dct[path] is True
    assert dct[SHVPath()] is True  # Intentional unused of path
    assert dct[SHVPath("some/node")] is False
    assert dct.get(SHVPath("some")) is None
    assert dct.get(tuple()) is None


def test_cmp():
    assert SHVPath() < "foo"
    assert SHVPath("alice") < SHVPath("foo")
    assert not SHVPath("foo") < "alice"
    assert SHVPath("foo") <= SHVPath("foo")
    assert SHVPath("foo") > SHVPath("alice")
    assert SHVPath("foo") >= SHVPath("foo")

    with pytest.raises(TypeError):
        assert SHVPath() < 1
    with pytest.raises(TypeError):
        assert SHVPath() <= 1
    with pytest.raises(TypeError):
        assert SHVPath() > 1
    with pytest.raises(TypeError):
        assert SHVPath() >= 1


def test_parents():
    path = SHVPath("some/node/here/after")
    assert list(path.parents) == [
        SHVPath("some/node/here"),
        SHVPath("some/node"),
        SHVPath("some"),
        SHVPath(""),
    ]
    assert SHVPath("some/node").parents[-1] == SHVPath("")
    assert SHVPath("some/node").parents[-2] == SHVPath("some")
    with pytest.raises(IndexError):
        SHVPath("some/node").parents[3]
    with pytest.raises(IndexError):
        SHVPath("some/node").parents[-3]
    assert path.parents[1:4:2] == (SHVPath("some/node"), SHVPath())


def test_parent():
    assert SHVPath("some/node/here").parent == "some/node"


def test_root_parent():
    """Root is its own parent."""
    root = SHVPath("")
    assert root is root.parent


def test_name():
    assert SHVPath("some/node/here").name == "here"


def test_suffix():
    assert SHVPath("some/node/here.txt").suffix == ".txt"


def test_suffixes():
    assert SHVPath("some/node/here.txt.tar.gz").suffixes == [".txt", ".tar", ".gz"]


def test_stem():
    assert SHVPath("some/node/here.txt.tar.gz").stem == "here"


def test_is_relative_to():
    assert SHVPath().is_relative_to("")
    assert SHVPath("some/node").is_relative_to("")
    assert SHVPath("some/node").is_relative_to("some")
    assert SHVPath("some/node").is_relative_to(SHVPath("some/node"))
    assert not SHVPath("some/node").is_relative_to("som")
    assert not SHVPath("some/node").is_relative_to("some/n")


def test_joinpath():
    assert SHVPath().joinpath("some", "node/here") == "some/node/here"


def test_full_match():
    assert SHVPath("some/node/here").full_match("some/**")
    assert not SHVPath("some/node/here").full_match("some/*")
    assert not SHVPath("some/node/here").full_match("*/here")


def test_match():
    assert SHVPath("some/node/here").match("node/*")
    assert not SHVPath("some/node/here").match("here/*")


def test_relative_to():
    assert SHVPath("some/node").relative_to("some") == "node"
    with pytest.raises(ValueError):
        assert SHVPath("some/node").relative_to(SHVPath("other"))


def test_with_name():
    assert SHVPath("some/node").with_name("other") == "some/other"
    with pytest.raises(ValueError):
        SHVPath().with_name("node")


def test_with_stem():
    assert SHVPath("some/node.txt.gz").with_stem("other") == "some/other.txt.gz"
    with pytest.raises(ValueError):
        SHVPath().with_stem("node")


def test_with_suffix():
    assert SHVPath("some/node.txt.gz").with_suffix(".xz") == "some/node.xz"
    with pytest.raises(ValueError):
        SHVPath().with_suffix(".xz")
