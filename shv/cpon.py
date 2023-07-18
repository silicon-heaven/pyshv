"""Cpon data format reader and writer."""
import collections.abc
import datetime
import decimal
import io
import typing

import dateutil.parser

from . import commonpack
from .value import SHVMeta, SHVMetaType, SHVType, SHVUInt


class Cpon:
    """Cpon constans and definitions."""

    ProtocolType = 2

    @classmethod
    def unpack(cls, data: bytes | str) -> SHVType:
        """Unpack single value from given data."""
        return CponReader.unpack(data)

    @classmethod
    def pack(cls, value: SHVType) -> bytes:
        """Pack given value and return bytes."""
        return CponWriter.pack(value)


class CponReader(commonpack.CommonReader):
    """Read data in Cpon format."""

    def _skip_white_insignificant(self):
        while True:
            b = self._peek_byte()
            if b == 0:
                return
            if b > ord(" "):
                if b == ord("/"):
                    self._peek_drop()
                    b = self._read_byte()
                    if b == ord("*"):
                        # multiline_comment_entered
                        while True:
                            b = self._read_byte()
                            if b == ord("*"):
                                b = self._read_byte()
                                if b == ord("/"):
                                    break
                    elif b == ord("/"):
                        # to end of line comment entered
                        while True:
                            b = self._read_byte()
                            if b == ord("\n"):
                                break
                    else:
                        raise TypeError("Malformed comment")
                elif b in (ord(":"), ord(",")):
                    self._peek_drop()
                    continue
                else:
                    break
            else:
                self._peek_drop()

    def read_meta(self) -> SHVMetaType | None:
        self._skip_white_insignificant()
        b = self._peek_byte()
        if b != ord("<"):
            return None
        return self._read_map(">")

    def read(self) -> SHVType:
        meta = self.read_meta()

        value: SHVType
        self._skip_white_insignificant()
        b = self._peek_byte()
        if ord("0") <= b <= ord("9") or b == ord("+") or b == ord("-"):
            value = self._new_read_number()
        elif b == ord('"'):
            value = self._read_cstring()
        elif b == ord("["):
            value = self._read_list()
        elif b == ord("{"):
            value = self._read_map()
        elif b == ord("i"):
            self._peek_drop()
            b = self._peek_byte()
            if b != ord("{"):
                raise TypeError("Invalid IMap prefix.")
            value = self._read_map()
        elif b == ord("d"):
            self._peek_drop()
            b = self._peek_byte()
            if b != ord('"'):
                raise TypeError("Invalid DateTime prefix.")
            value = self._read_datetime()
        elif b == ord("b"):
            self._peek_drop()
            b = self._peek_byte()
            if b != ord('"'):
                raise TypeError("Invalid Blob prefix.")
            value = self._read_blob()
        elif b == ord("x"):
            self._peek_drop()
            b = self._peek_byte()
            if b != ord('"'):
                raise TypeError("Invalid HexBlob prefix.")
            value = self._read_hexblob()
        elif b == ord("t"):
            self._read_check(b"true")
            value = True
        elif b == ord("f"):
            self._read_check(b"false")
            value = False
        elif b == ord("n"):
            self._read_check(b"null")
            value = None
        else:
            raise TypeError("Malformed Cpon input.")
        if meta is not None:
            value = SHVMeta.new(value, meta)
        return value

    def _read_datetime(self):
        self._peek_drop()  # eat '"'
        date = ""
        while True:
            c = chr(self._read_byte())
            if c == '"':
                break
            date += c
        return dateutil.parser.isoparse(date)

    @staticmethod
    def _hexdigit_to_int(b: int) -> int:
        if ord("0") <= b <= ord("9"):
            val = b - 48
        elif ord("a") <= b <= ord("f"):
            val = b - ord("a") + 10
        elif ord("A") <= b <= ord("F"):
            val = b - ord("A") + 10
        else:
            raise ValueError(f"Invalid HEX digit: {chr(b)}")
        return val

    def _read_blob(self) -> bytes:
        self._peek_drop()
        res = bytearray()
        while True:
            b = self._read_byte()
            if b == ord("\\"):
                b = self._read_byte()
                if b == ord("\\"):
                    res += b"\\"
                elif b == ord('"'):
                    res += b'"'
                elif b == ord("n"):
                    res += b"\n"
                elif b == ord("r"):
                    res += b"\r"
                elif b == ord("t"):
                    res += b"\t"
                else:
                    hi = b
                    lo = self._read_byte()
                    res.append(
                        16 * CponReader._hexdigit_to_int(hi)
                        + CponReader._hexdigit_to_int(lo)
                    )
            else:
                if b == ord('"'):
                    break  # end of string
                res.append(b)
        return bytes(res)

    def _read_hexblob(self) -> bytes:
        res = bytearray()
        self._peek_drop()
        while True:
            b = self._read_byte()
            if b == ord('"'):
                # end of string
                break
            hi = b
            lo = self._read_byte()
            res.append(
                16 * CponReader._hexdigit_to_int(hi) + CponReader._hexdigit_to_int(lo)
            )
        return bytes(res)

    def _read_cstring(self) -> str:
        res = bytearray()
        self._peek_drop()  # eat '"'
        while True:
            b = self._read_byte()
            if b == ord("\\"):
                b = self._read_byte()
                if b == ord("\\"):
                    res += b"\\"
                elif b == ord("b"):
                    res += b"\b"
                elif b == ord('"'):
                    res += b'"'
                elif b == ord("f"):
                    res += b"\f"
                elif b == ord("n"):
                    res += b"\n"
                elif b == ord("r"):
                    res += b"\r"
                elif b == ord("t"):
                    res += b"\t"
                elif b == ord("0"):
                    res += b"\0"
                else:
                    res += bytes((b,))
            else:
                if b == ord('"'):
                    break  # end of string
                res += bytes((b,))
        # Note: this is required to correctly decode the UTF-8 string that contains
        # multiple bytes.
        return res.decode("utf-8")

    def _read_list(self):
        res = []
        self._peek_drop()
        while True:
            self._skip_white_insignificant()
            b = self._peek_byte()
            if b == ord("]"):
                self._peek_drop()
                break
            res.append(self.read())
        return res

    def _read_map(self, terminator="}"):
        res = {}
        self._peek_drop()
        while True:
            self._skip_white_insignificant()
            b = self._peek_byte()
            if b == ord(terminator):
                self._peek_drop()
                break
            key = self.read()
            self._skip_white_insignificant()
            val = self.read()
            res[key] = val
        return res

    def _new_read_number(self) -> int | SHVUInt | decimal.Decimal:
        bval = bytearray()

        def accept(possib: bytes) -> int | None:
            b = self._peek_byte()
            if b not in possib:
                return None
            bval.append(self._read_byte())
            return b

        tp: typing.Type = int
        parsed = False
        nonempty = False
        accept(b"-+")
        if accept(b"0") is not None:
            if accept(b"x") is not None:
                while accept(b"0123456789AaBbCcDdEeFf") is not None:
                    nonempty = True
                parsed = True
            elif accept(b"b"):
                while accept(b"01"):
                    nonempty = True
                parsed = True
        if not parsed:
            exp = False
            while True:
                lb = accept(
                    b"0123456789.ueE"
                    if tp == int
                    else b"0123456789"
                    if exp
                    else b"0123456789eE"
                )
                if lb == ord("."):
                    tp = decimal.Decimal
                elif lb in (ord("e"), ord("E")):
                    tp = decimal.Decimal
                    accept(b"-+")
                    exp = True
                elif lb == ord("u"):
                    tp = SHVUInt
                    bval.pop()  # remove "u" from bytes
                    break
                elif lb is None:
                    break
                nonempty = True
        if not nonempty:
            bval.append(ord("0"))

        if tp in (int, SHVUInt):
            return tp(bval, 0)
        if tp == decimal.Decimal:
            return tp(bval.decode("ascii"))
        assert False  # should be unreachable


class CponWriter(commonpack.CommonWriter):
    """Write data in Cpon format."""

    class Options:
        """Options for the CponWriter.

        :param indent: bytes or string used to indent the code.
        """

        def __init__(self, indent: None | str | bytes = None):
            self.indent = indent.encode() if isinstance(indent, str) else indent

    def __init__(self, stream: io.IOBase | None = None, options: Options | None = None):
        super().__init__(stream)
        self.options = options if options is not None else self.Options()
        self._nest_level = 0

    def _indent_item(self, is_online_container: bool, item_index: int) -> None:
        if not self.options.indent:
            return
        if is_online_container:
            if item_index > 0:
                self._writestr(" ")
        else:
            self._writestr("\n")
            self._write(self.options.indent * self._nest_level)

    def write_meta(self, meta: dict) -> None:
        self._writestr("<")
        self._write_map_content(meta)
        self._writestr(">")

    def write_null(self) -> None:
        self._writestr("null")

    def write_bool(self, value: bool) -> None:
        self._writestr("true" if value else "false")

    def write_blob(self, value: bytes | bytearray) -> None:
        self._writestr('b"')
        for d in value:
            if d >= 0x7F:
                self._writestr("\\")
                self._writestr(self._nibble_to_hexdigit(d // 16))
                self._writestr(self._nibble_to_hexdigit(d % 16))
            else:
                self._writestr(
                    {
                        ord("\0"): "\\0",
                        ord("\\"): "\\\\",
                        ord("\t"): "\\t",
                        ord("\b"): "\\b",
                        ord("\r"): "\\r",
                        ord("\n"): "\\n",
                        ord('"'): '\\"',
                    }.get(d, chr(d))
                )
        self._writestr('"')

    @staticmethod
    def _nibble_to_hexdigit(b: int) -> str:
        if b >= 0:
            if b < 10:
                return chr(b + ord("0"))
            if b < 16:
                return chr(b - 10 + ord("a"))
        raise ValueError(f"Invalid nibble value: {b}")

    def write_string(self, value: str) -> None:
        self.write_cstring(value)

    def write_cstring(self, value: str) -> None:
        self._writestr('"')
        for d in value:
            self._writestr(
                {
                    "\0": "\\0",
                    "\\": "\\\\",
                    "\t": "\\t",
                    "\b": "\\b",
                    "\r": "\\r",
                    "\n": "\\n",
                    '"': '\\"',
                }.get(d, d)
            )
        self._writestr('"')

    def write_int(self, value: int) -> None:
        self._writestr(str(value))

    def write_uint(self, value: int) -> None:
        self._writestr(f"{value}u")

    def write_double(self, value: float) -> None:
        self._writestr(str(value))

    def write_decimal(self, value: decimal.Decimal) -> None:
        sval = str(value)
        if not any(c in ".eE" for c in sval):
            sval = sval + ".0"
        self._writestr(sval)

    def write_datetime(self, value: datetime.datetime) -> None:
        # TODO possibly just use datetime iso format
        self._writestr('d"')
        DT_LEN = 19
        dt_str = value.isoformat()
        self._writestr(dt_str[:DT_LEN])
        dt_str = dt_str[DT_LEN:]
        if len(dt_str) > 0 and dt_str[0] == ".":
            self._writestr(dt_str[:4])
            dt_str = dt_str[7:]
        if dt_str[:6] == "+00:00":
            self._writestr("Z")
        elif dt_str[:1] == "Z":
            self._writestr(dt_str)
        elif dt_str[:1] == "+" or dt_str[:1] == "-":
            self._writestr(dt_str[:3])
            min_part = dt_str[4:6]
            if min_part != "00":
                self._writestr(min_part)
        self._writestr('"')

    def write_list(self, value: collections.abc.Collection[SHVType]) -> None:
        self._nest_level += 1
        is_oneliner = self._is_oneline_list(value)
        self._writestr("[")
        for i, v in enumerate(value):
            if i > 0:
                self._writestr(",")
            self._indent_item(is_oneliner, i)
            self.write(v)
        self._nest_level -= 1
        self._indent_item(is_oneliner, 0)
        self._writestr("]")

    @staticmethod
    def _is_oneline_list(lst) -> bool:
        return len(lst) <= 10 and all(not isinstance(v, (list, dict)) for v in lst)

    def write_imap(self, value: collections.abc.Mapping[int, SHVType]) -> None:
        self._writestr("i{")
        self._write_map_content(value)
        self._writestr("}")

    def write_map(self, value: collections.abc.Mapping[str, SHVType]) -> None:
        self._writestr("{")
        self._write_map_content(value)
        self._writestr("}")

    @staticmethod
    def _is_oneline_map(mmap) -> bool:
        return len(mmap) <= 10 and all(
            not isinstance(v, (list, dict)) for v in mmap.values()
        )

    def _write_map_content(self, mmap) -> None:
        self._nest_level += 1
        is_oneliner = self._is_oneline_map(mmap)
        i = -1
        for ikey in sorted(k for k in mmap.keys() if isinstance(k, int)):
            i += 1
            if i > 0:
                self._writestr(",")
            self._indent_item(is_oneliner, i)
            self.write_int(ikey)
            self._writestr(":")
            self.write(mmap[ikey])
        for skey in sorted(k for k in mmap.keys() if isinstance(k, str)):
            i += 1
            if i > 0:
                self._writestr(",")
            self._indent_item(is_oneliner, i)
            self._writestr('"')
            self._writestr(skey)
            self._writestr('":')
            self.write(mmap[skey])
        self._nest_level -= 1
        self._indent_item(is_oneliner, 0)
