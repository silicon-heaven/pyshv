"""We are using :func:`binascii.crc32` but check if it is really CRC-32."""

import binascii

import pytest


@pytest.mark.parametrize(
    "data,crc",
    (
        (b"", 0x0),
        (b"1", 0x83DCEFB7),
        (b"123456789", 0xCBF43926),
    ),
)
def test(data, crc):
    """Test that :func:`binascii.crc32` provides implementation we need."""
    assert binascii.crc32(data) == crc
