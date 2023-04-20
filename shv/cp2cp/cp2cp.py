"""The implementation of conversion."""
import enum
import pathlib
import typing

from ..chainpack import ChainPackReader, ChainPackWriter
from ..cpon import CponReader, CponWriter


class CPFormat(enum.Enum):
    """The specified for the format we should convert to."""

    CPON = enum.auto()
    CHAINPACK = enum.auto()


def convert(
    inp: str | bytes | pathlib.Path | typing.IO,
    inf: CPFormat,
    outp: None | pathlib.Path | typing.IO,
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
    :returns: Bytes in case `odata` was `None` otherwise `None`.
    """
    idata: bytes
    if isinstance(inp, bytes):
        idata = inp
    elif isinstance(inp, str):
        idata = inp.encode("utf-8")
    elif isinstance(inp, pathlib.Path):
        with inp.open("rb") as f:
            idata = f.read()
    else:
        idata = inp.read()
        if isinstance(idata, str):
            idata = idata.encode("utf-8")
    rd: CponReader | ChainPackReader = (
        CponReader(idata) if inf.CPON else ChainPackReader(idata)
    )
    wr: CponWriter | ChainPackWriter = (
        CponWriter(cpon_options) if outf.CPON else ChainPackWriter()
    )
    wr.write(rd.read())
    if outp is None:
        return wr.data_bytes()
    if isinstance(outp, pathlib.Path):
        with outp.open("wb") as f:
            f.write(wr.data_bytes())
    else:
        outp.write(wr.data_bytes())
    return None
