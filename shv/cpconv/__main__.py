"""Implementation of CPON ChainPack conversion tool."""

import argparse
import functools
import sys

from .. import cpon
from ..__version__ import VERSION
from .cpconv import CPFormat, convert


def parse_args() -> argparse.Namespace:
    """Parse passed arguments and return result."""
    parser = argparse.ArgumentParser(
        "pycp2cp2", description="Chainpack to Cpon and vice versa converter"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    igroup = parser.add_mutually_exclusive_group()
    ogroup = parser.add_mutually_exclusive_group()
    igroup.add_argument(
        "--ic",
        "--input-chainpack",
        action="store_true",
        help="Input is in Chainpack format (default if no input set).",
    )
    ogroup.add_argument(
        "--oc",
        "--output-chainpack",
        action="store_true",
        help="Output is in Chainpack format.",
    )
    igroup.add_argument(
        "--ip",
        "--input-cpon",
        action="store_true",
        help="Input is in Cpon format.",
    )
    ogroup.add_argument(
        "--op",
        "--output-cpon",
        action="store_true",
        help="Output is in Cpon format (default if no output set).",
    )
    parser.add_argument(
        "-i",
        "--indent-cpon",
        action="store",
        default="",
        help='Indent used when generating Cpon (default is no-indent "")',
    )
    parser.add_argument(
        "--o",
        "--output",
        default="-",
        type=argparse.FileType("wb"),
        help="Output file (stdout is used if not specified).",
    )
    parser.add_argument(
        "INPUT",
        type=argparse.FileType("rb"),
        help="Input file for conversion.",
    )
    return parser.parse_args()


def main() -> int:
    """Application's entrypoint."""
    args = parse_args()

    inf = CPFormat.CPON if not args.ic else CPFormat.CHAINPACK
    outf = CPFormat.CPON if not args.oc else CPFormat.CHAINPACK

    indent_cpon = functools.reduce(
        lambda s, repl: s.replace(*repl),
        (("\\t", "\t"), ("\\r", "\r"), ("\\n", "\n")),
        args.indent_cpon,
    )
    cpon_options = cpon.CponWriter.Options(indent=indent_cpon)

    convert(args.INPUT, inf, args.o, outf, cpon_options)
    return 0


if __name__ == "__main__":
    sys.exit(main())
