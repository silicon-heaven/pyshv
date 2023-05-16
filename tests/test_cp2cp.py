"""Check usability of our stream conversion."""
import pytest

from shv.cp2cp import CPFormat, convert

DATA = [
    ("true", b"\xfe"),
    ("[1]", b"\x88A\xff"),
]


@pytest.mark.parametrize("cpon,chainpack", DATA)
def test_cp2cpon(cpon, chainpack):
    assert (
        convert(chainpack, CPFormat.CHAINPACK, None, CPFormat.CPON).decode("utf-8")
        == cpon
    )


@pytest.mark.parametrize("cpon,chainpack", DATA)
def test_cpon2cp(cpon, chainpack):
    assert convert(cpon, CPFormat.CPON, None, CPFormat.CHAINPACK) == chainpack
