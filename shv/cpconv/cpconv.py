"""The implementation of conversion."""

import enum
import io
import pathlib
import typing

from ..chainpack import ChainPackReader, ChainPackWriter
from ..commonpack import CommonReader, CommonWriter
from ..cpon import CponReader, CponWriter


class CPFormat(enum.Enum):
    """The specified for the format we should convert to."""

    CPON = enum.auto()
    CHAINPACK = enum.auto()


def convert(
    inp: str | bytes | pathlib.Path | typing.IO,
    inf: CPFormat,
    outp: pathlib.Path | typing.IO | None,
    outf: CPFormat,
    cpon_options: CponWriter.Options | None = None,
) -> bytes | None:
    """Convert ChainPack to Cpon or vice versa.

    This also allows conversion from the same type to the same one. This can be
    used to validate format for example.

    :param inp: Input data in ChainPack or Cpon or path to the file with them.
    :param inf: Input data format.
    :param outp: Ouput where `None` results in data returned from the function
        and file or IO into the write to those.
    :param outf: Output data format.
    :param options: Cpon writer options. This is used only when:
        `outf == CPFormat.CPON`.
    :return: Bytes in case `odata` was `None` otherwise `None`.
    """
    if isinstance(inp, str):
        inp = inp.encode("utf-8")

    istream: typing.IO
    if isinstance(inp, bytes):
        istream = io.BytesIO(inp)
    elif isinstance(inp, pathlib.Path):
        istream = inp.open("rb")
    else:
        istream = inp

    ostream: typing.IO
    if outp is None:
        ostream = io.BytesIO()
    elif isinstance(outp, pathlib.Path):
        ostream = outp.open("wb")
    else:
        ostream = outp

    rd: CommonReader = (
        CponReader(istream) if inf is CPFormat.CPON else ChainPackReader(istream)
    )
    wr: CommonWriter = (
        CponWriter(ostream, cpon_options)
        if outf is CPFormat.CPON
        else ChainPackWriter(ostream)
    )

    wr.write(rd.read())

    if isinstance(ostream, io.BytesIO):
        return ostream.getvalue()
    if isinstance(outp, pathlib.Path):
        ostream.close()
    return None
