#!/usr/bin/env python3
import os
import sys

from shv.chainpack import ChainPackReader, ChainPackWriter
from shv.cpon import CponReader, CponWriter


def errprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


help_msg = """cp2cp.py - ChainPack to Cpon and vice versa converter

USAGE:
-i "indent_string"
 indent Cpon (default is no-indent "")
--ip
 input stream is Cpon (ChainPack otherwise)
--oc
 write output in ChainPack (Cpon otherwise)
"""


def help_exit(exit_code=os.EX_OK):
    print(help_msg)
    sys.exit(exit_code)


def cp2cp():
    o_indent = None
    o_chainpack_output = False
    o_cpon_input = False
    o_file_name = None
    args = sys.argv[1:]

    class OutOfArgsException(Exception):
        pass

    class InvalidCLIArg(Exception):
        def __init__(self, msg):
            self.message = msg

    def get_arg(error_msg=""):
        nonlocal args
        if len(args):
            ret = args[0]
            args = args[1:]
            return ret
        elif error_msg:
            raise InvalidCLIArg("Missing value for CLI option: " + error_msg)
        else:
            return None

    try:
        while True:
            arg = get_arg()
            if arg is None:
                break
            if arg[:2] == "--":
                arg = arg[2:]
                if arg == "ip":
                    o_cpon_input = True
                elif arg == "oc":
                    o_chainpack_output = True
                elif arg == "help":
                    help_exit()
                else:
                    raise InvalidCLIArg("--" + arg)
            elif arg[:1] == "-":
                arg = arg[1:]
                if arg == "i":
                    o_indent = get_arg("Indent string")
                    o_indent = o_indent.replace("\\t", "\t")
                    o_indent = o_indent.replace("\\r", "\r")
                    o_indent = o_indent.replace("\\n", "\n")
                elif arg == "h":
                    help_exit()
                else:
                    raise InvalidCLIArg("-" + arg)
            else:
                if o_file_name:
                    raise InvalidCLIArg("input file name set already")
                o_file_name = arg
    except OutOfArgsException:
        pass
    except InvalidCLIArg as e:
        errprint("InvalidCLIArg:", e.message)
        help_exit(os.EX_DATAERR)

    if o_file_name:
        data = open(o_file_name, "rb").read()
    else:
        data = sys.stdin.buffer.read()
    # errprint(type(data))
    if o_cpon_input:
        rd = CponReader(data)
    else:
        rd = ChainPackReader(data)

    if o_chainpack_output:
        wr = ChainPackWriter()
    else:
        opts = CponWriter.Options(indent=o_indent)
        wr = CponWriter(opts)

    # try:
    val = rd.read()
    wr.write(val)
    sys.stdout.buffer.write(wr.data_bytes())


if __name__ == "__main__":
    cp2cp()
