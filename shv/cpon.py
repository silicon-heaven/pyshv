"""Cpon data format reader and writer."""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import decimal
import io
import typing

from . import commonpack
from .value import (
    SHVIMap,
    SHVIMapType,
    SHVListType,
    SHVMap,
    SHVMapType,
    SHVMeta,
    SHVMetaType,
    SHVType,
    SHVUInt,
)


class Cpon:
    """Cpon constans and definitions."""

    ProtocolType = 2

    @classmethod
    def unpack(cls, data: bytes | str) -> SHVType:
        """Unpack single value from given data."""
        return CponReader.unpack(data)

    @classmethod
    def pack(cls, value: SHVType, options: CponWriter.Options | None = None) -> str:
        """Pack given value and return string."""
        stream = io.BytesIO()
        self = CponWriter(stream, options)
        self.write(value)
        return stream.getvalue().decode("utf-8")


class CponReader(commonpack.CommonReader):
    """Read data in Cpon format."""

    def _skip_white_insignificant(self) -> None:
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
                        raise ValueError("Malformed comment")
                elif b in {ord(":"), ord(",")}:
                    self._peek_drop()
                    continue
                else:
                    break
            else:
                self._peek_drop()

    def read_meta(self) -> SHVMetaType | None:  # noqa: D102
        self._skip_white_insignificant()
        b = self._peek_byte()
        if b != ord("<"):
            return None
        return self._read_map(">")

    def read(self) -> SHVType:  # noqa: D102
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
            value = typing.cast(SHVMapType, self._read_map())
            if not value:
                value = SHVMap()  # Remove confusin between map and imap
        elif b == ord("i"):
            self._peek_drop()
            b = self._peek_byte()
            if b != ord("{"):
                raise ValueError("Invalid IMap prefix.")
            value = typing.cast(SHVIMapType, self._read_map())
            if not value:
                value = SHVIMap()  # Remove confusin between map and imap
        elif b == ord("d"):
            self._peek_drop()
            b = self._peek_byte()
            if b != ord('"'):
                raise ValueError("Invalid DateTime prefix.")
            value = self._read_datetime()
        elif b == ord("b"):
            self._peek_drop()
            b = self._peek_byte()
            if b != ord('"'):
                raise ValueError("Invalid Blob prefix.")
            value = self._read_blob()
        elif b == ord("x"):
            self._peek_drop()
            b = self._peek_byte()
            if b != ord('"'):
                raise ValueError("Invalid HexBlob prefix.")
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
            raise ValueError("Malformed Cpon input.")
        if meta is not None:
            value = SHVMeta.new(value, meta)
        return value

    def _read_datetime(self) -> datetime.datetime:
        self._peek_drop()  # eat '"'
        date = ""
        while True:
            c = chr(self._read_byte())
            if c == '"':
                break
            date += c
        return datetime.datetime.fromisoformat(date)

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

    def _read_list(self) -> SHVListType:
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

    def _read_map(self, terminator: str = "}") -> dict[str | int, SHVType]:
        res: dict[str | int, SHVType] = {}
        self._peek_drop()
        while True:
            self._skip_white_insignificant()
            b = self._peek_byte()
            if b == ord(terminator):
                self._peek_drop()
                break
            key = self.read()
            if not isinstance(key, str | int):
                raise ValueError(f"Invalid Map key: {type(key)}")
            self._skip_white_insignificant()
            val = self.read()
            res[key] = val
        return res

    def _new_read_number(self) -> int | SHVUInt | float | decimal.Decimal:
        bval = bytearray()

        def accept(possib: bytes) -> bool:
            b = self._peek_byte()
            if b not in possib:
                return False
            bval.append(self._read_byte())
            return b is not None

        def multiaccept(possib: bytes) -> None:
            while accept(possib):
                pass

        cset_dec = b"0123456789"
        cset_hex = b"0123456789AaBbCcDdEeFf"
        cset_bin = b"01"

        cset = cset_dec
        accept(b"-+")
        if accept(b"0"):
            if accept(b"x"):
                cset = cset_hex
            elif accept(b"b"):
                cset = cset_bin
        multiaccept(cset)
        if dot := accept(b"."):
            multiaccept(cset)
        tp: type = int
        if cset is not cset_bin and accept(b"pP"):
            tp = float
            accept(b"+-")
            multiaccept(cset_dec)
        elif accept(b"eE"):
            if cset is not cset_dec:
                raise ValueError("Decimal number must be decimal")
            tp = decimal.Decimal
            accept(b"+-")
            multiaccept(cset_dec)
        elif dot:
            tp = decimal.Decimal
        elif self._peek_byte() == ord("u"):
            self._read_byte()
            tp = SHVUInt

        if tp is float:
            sval = bval.decode("ascii")
            if cset is cset_hex:
                return float.fromhex(sval)
            mant, _, exp = sval.replace("P", "p").partition("p")
            return float(mant) * (2.0 ** int(exp))
        if tp is decimal.Decimal:
            return tp(bval.decode("ascii"))  # type: ignore
        return tp(bval, 0)  # type: ignore


class CponWriter(commonpack.CommonWriter):
    """Write data in Cpon format."""

    @dataclasses.dataclass
    class Options:
        """Options for the CponWriter."""

        indent: bytes = b""
        """Bytes or string used to indent the code."""

    def __init__(
        self, stream: typing.IO | None = None, options: Options | None = None
    ) -> None:
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

    def write_meta(self, meta: SHVMetaType) -> None:  # noqa: D102
        self._writestr("<")
        self._write_map_content(meta)
        self._writestr(">")

    def write_null(self) -> None:  # noqa: D102
        self._writestr("null")

    def write_bool(self, value: bool) -> None:  # noqa: D102
        self._writestr("true" if value else "false")

    def write_blob(self, value: bytes | bytearray) -> None:  # noqa: D102
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

    def write_string(self, value: str) -> None:  # noqa: D102
        self.write_cstring(value)

    def write_cstring(self, value: str) -> None:  # noqa: D102
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

    def write_int(self, value: int) -> None:  # noqa: D102
        self._writestr(str(value))

    def write_uint(self, value: int) -> None:  # noqa: D102
        self._writestr(f"{value}u")

    def write_double(self, value: float) -> None:  # noqa: D102
        mant, p, exp = value.hex().partition("p")
        self._writestr(f"{mant.rstrip('0')}{p}{exp}")

    def write_decimal(self, value: decimal.Decimal) -> None:  # noqa: D102
        sval = str(value)
        if not any(c in ".eE" for c in sval):
            sval += ".0"
        self._writestr(sval)

    def write_datetime(self, value: datetime.datetime) -> None:  # noqa: D102
        # We perform here some modification to make the format more compact in
        # some cases. This is not essentailly required but makes it more
        # compatible with other implementations.
        self._writestr('d"')
        rstr = value.isoformat(
            timespec="milliseconds" if value.microsecond else "seconds"
        )
        rlen = 23 if value.microsecond else 19
        self._writestr(rstr[:rlen])
        rstr = rstr[rlen:]
        if rstr[:6] == "+00:00":
            self._writestr("Z")
        elif rstr[:1] == "Z":
            self._writestr(rstr)
        elif rstr[:1] == "+" or rstr[:1] == "-":
            self._writestr(rstr[:3])
            if (mpart := rstr[4:6]) != "00":
                self._writestr(mpart)
        self._writestr('"')

    def write_list(self, value: SHVListType) -> None:  # noqa: D102
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
    def _is_oneline_list(lst: collections.abc.Sequence[SHVType]) -> bool:
        return len(lst) <= 10 and all(not isinstance(v, list | dict) for v in lst)

    def write_imap(self, value: SHVIMapType) -> None:  # noqa: D102
        self._writestr("i{")
        self._write_map_content(value)
        self._writestr("}")

    def write_map(self, value: SHVMapType) -> None:  # noqa: D102
        self._writestr("{")
        self._write_map_content(value)
        self._writestr("}")

    @staticmethod
    def _is_oneline_map(mmap: collections.abc.Mapping) -> bool:
        return len(mmap) <= 10 and all(
            not isinstance(v, list | dict) for v in mmap.values()
        )

    def _write_map_content(self, mmap: collections.abc.Mapping) -> None:
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
