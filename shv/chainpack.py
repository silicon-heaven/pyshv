"""Chainpack data format reader and writer."""

from __future__ import annotations

import datetime
import decimal
import enum
import io
import struct
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
    decimal_rexp,
)


class ChainPack:
    """ChainPack constans and definitions."""

    ProtocolType = 1

    class Schema(enum.IntEnum):
        """The packing schema type association."""

        CP_Null = 128
        CP_UInt = 129
        CP_Int = 130
        CP_Double = 131
        CP_Bool = 132
        CP_Blob = 133
        CP_String = 134  # utf8 encoded string
        CP_List = 136
        CP_Map = 137
        CP_IMap = 138
        CP_MetaMap = 139
        CP_Decimal = 140
        CP_DateTime = 141
        CP_CString = 142
        CP_FALSE = 253
        CP_TRUE = 254
        CP_TERM = 255

    # UTC msec since 2.2. 2018
    # Fri Feb 02 2018 00:00:00 == 1517529600 EPOCH
    SHV_EPOCH_SEC = 1517529600
    # ChainPack.INVALID_MIN_OFFSET_FROM_UTC = (-64 * 15)

    @staticmethod
    def unpack(data: bytes | str) -> SHVType:
        """Unpack single value from given data."""
        return ChainPackReader.unpack(data)

    @staticmethod
    def pack(value: SHVType) -> bytes:
        """Pack given value and return bytes."""
        return ChainPackWriter.pack(value)

    @staticmethod
    def unpack_uint_data(data: bytes | bytearray) -> int:
        """Unpack given value as unsigned int data.

        The existence of this is pretty much just to support Stream transport
        protocol for SHV RPC. You probably do not want to use this for anything
        else.

        :param data: Data that should contain unsigned integer in Chainpack
          format. Unused bytes at the end are ignored.
        :return: unpacked integer.
        :raise ValueError: in case of invalid data.
        """
        try:
            return ChainPackReader(data).read_uint_data()
        except EOFError as exc:
            raise ValueError from exc

    @staticmethod
    def pack_uint_data(value: int) -> bytes:
        """Pack given value as unsigned int data.

        The existence of this is pretty much just to support Stream transport
        protocol for SHV RPC. You probably do not want to use this for anything
        else.

        :param value: Unsigned integer to be packed.
        :return: bytes with unsigned integer.
        """
        bio = io.BytesIO()
        writer = ChainPackWriter(bio)
        writer.write_uint_data(value)
        return bio.getvalue()


class ChainPackReader(commonpack.CommonReader):
    """Read data in ChainPack format."""

    def read_meta(self) -> SHVMetaType | None:  # noqa: D102
        if self._peek_byte() != ChainPack.Schema.CP_MetaMap:
            return None
        self._peek_drop()
        return self._read_map()

    def read(self) -> SHVType:  # noqa: D102
        meta = self.read_meta()

        value: SHVType
        packing_schema = self._read_byte()
        if packing_schema < 128:
            # tiny Int or UInt
            value = packing_schema & 63
            if not packing_schema & 64:
                value = SHVUInt(value)
        elif packing_schema == ChainPack.Schema.CP_Null:
            value = None
        elif packing_schema == ChainPack.Schema.CP_TRUE:
            value = True
        elif packing_schema == ChainPack.Schema.CP_FALSE:
            value = False
        elif packing_schema == ChainPack.Schema.CP_Int:
            value = self._read_int_data()
        elif packing_schema == ChainPack.Schema.CP_UInt:
            value = SHVUInt(self.read_uint_data())
        elif packing_schema == ChainPack.Schema.CP_Double:
            value = self._read_double()
        elif packing_schema == ChainPack.Schema.CP_Decimal:
            value = self._read_decimal()
        elif packing_schema == ChainPack.Schema.CP_DateTime:
            value = self._read_datetime()
        elif packing_schema == ChainPack.Schema.CP_Map:
            value = typing.cast(SHVMapType, self._read_map())
            if not value:
                value = SHVMap()  # Remove confusin between map and imap
        elif packing_schema == ChainPack.Schema.CP_IMap:
            value = typing.cast(SHVIMapType, self._read_map())
            if not value:
                value = SHVIMap()  # Remove confusin between map and imap
        elif packing_schema == ChainPack.Schema.CP_List:
            value = self._read_list()
        elif packing_schema == ChainPack.Schema.CP_Blob:
            value = self._read_blob()
        elif packing_schema == ChainPack.Schema.CP_String:
            value = self._read_string()
        elif packing_schema == ChainPack.Schema.CP_CString:
            value = self._read_cstring()
        else:
            raise ValueError(f"ChainPack - Invalid type: {packing_schema}")
        if meta is not None:
            value = SHVMeta.new(value, meta)
        return value

    def _read_uint_data_helper(self) -> tuple[int, int]:
        num = 0
        bitlen = 0
        head = self._read_byte()
        if (head & 128) == 0:
            bytes_to_read_cnt = 0
            num = head & 127
            bitlen = 7
        elif (head & 64) == 0:
            bytes_to_read_cnt = 1
            num = head & 63
            bitlen = 6 + 8
        elif (head & 32) == 0:
            bytes_to_read_cnt = 2
            num = head & 31
            bitlen = 5 + 2 * 8
        elif (head & 16) == 0:
            bytes_to_read_cnt = 3
            num = head & 15
            bitlen = 4 + 3 * 8
        else:
            bytes_to_read_cnt = (head & 0xF) + 4
            bitlen = bytes_to_read_cnt * 8

        for _ in range(bytes_to_read_cnt):
            r = self._read_byte()
            num = (num << 8) + r
        return num, bitlen

    def read_uint_data(self) -> int:  # noqa: D102
        num, _ = self._read_uint_data_helper()
        return num

    def _read_int_data(self) -> int:
        num, bitlen = self._read_uint_data_helper()
        sign_bit_mask = 1 << (bitlen - 1)
        neg = num & sign_bit_mask
        snum = num
        if neg:
            snum &= ~sign_bit_mask
            snum = -snum
        return snum

    def _read_double(self) -> float:
        res = struct.unpack("<d", self._read(8))  # little endian
        return typing.cast(float, res[0])

    def _read_decimal(self) -> decimal.Decimal:
        mant = self._read_int_data()
        exp = self._read_int_data()
        return decimal.Decimal(f"{mant}e{exp}")

    def _read_datetime(self) -> datetime.datetime:
        d = self._read_int_data()
        offset = 0
        has_tz_offset = d & 1
        has_not_msec = d & 2
        d >>= 2
        if has_tz_offset:
            offset = d & 0x7F
            if offset >= 128:
                offset -= 128  # sign extension
            d >>= 7
        f: float = d if has_not_msec else d / 1000
        f += ChainPack.SHV_EPOCH_SEC
        tzone = datetime.timezone(datetime.timedelta(minutes=offset * 15))
        return datetime.datetime.fromtimestamp(f, tzone)

    def _read_blob(self) -> bytes:
        dlen = self.read_uint_data()
        return self._read(dlen) if dlen else b""

    def _read_string(self) -> str:
        slen = self.read_uint_data()
        if slen <= 0:
            return ""
        return self._read(slen).decode("utf-8")

    def _read_cstring(self) -> str:
        res = ""
        while True:
            b = self._read_byte()
            if b == ord("\\"):
                b = self._read_byte()
                if b == ord("\\"):
                    res += "\\"
                elif b == ord("0"):
                    res += "\0"
                else:
                    res += chr(b)
            else:
                if b == 0:
                    break  # end of string
                res += chr(b)
        return res

    def _read_list(self) -> SHVListType:
        lst = []
        while True:
            b = self._peek_byte()
            if b == ChainPack.Schema.CP_TERM:
                self._read_byte()
                break
            lst.append(self.read())
        return lst

    def _read_map(self) -> dict[str | int, SHVType]:
        mmap: dict[str | int, SHVType] = {}
        while True:
            b = self._peek_byte()
            if b == ChainPack.Schema.CP_TERM:
                self._read_byte()
                break
            key = self.read()
            if not isinstance(key, str | int) or isinstance(key, SHVUInt):
                raise ValueError(f"Invalid Map key: {type(key)}")
            val = self.read()
            mmap[key] = val
        return mmap


class ChainPackWriter(commonpack.CommonWriter):
    """Write data in ChainPack format."""

    # Integer encoding:
    #  0 ...  7 bits  1  byte  |0|s|x|x|x|x|x|x|<-- LSB
    #  8 ... 14 bits  2  bytes |1|0|s|x|x|x|x|x| |x|x|x|x|x|x|x|x|<-- LSB
    # 15 ... 21 bits  3  bytes |1|1|0|s|x|x|x|x| |x|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x|<-- LSB
    # 22 ... 28 bits  4  bytes |1|1|1|0|s|x|x|x| |x|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x|<-- LSB
    # 29+       bits  5+ bytes |1|1|1|1|n|n|n|n| |s|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x| ... <-- LSB
    #                                         n ==  0 ->  4 bytes number (32 bit number)
    #                                         n ==  1 ->  5 bytes number
    #                                         n == 14 -> 18 bytes number
    #                                         n == 15 -> for future (number of bytes will be specified in next byte)

    @classmethod
    def _bytes_needed(cls, bit_len: int) -> int:
        """Calculate needed maximum number of bytes.

        Return max bit length >= bit_len, which can be encoded by same number of
        bytes number of bytes needed to encode bit_len.
        """
        if bit_len <= 28:
            cnt = ((bit_len - 1) // 7) + 1
        else:
            cnt = ((bit_len - 1) // 8) + 2
        return cnt or 1  # Always at least one byte is needed

    @classmethod
    def _expand_bit_len(cls, bit_len: int) -> int:
        byte_cnt = cls._bytes_needed(bit_len)
        if bit_len <= 28:
            ret = byte_cnt * (8 - 1) - 1
        else:
            ret = (byte_cnt - 1) * 8 - 1
        return ret

    def _write_uint_data_helper(self, num: int, bit_len: int) -> None:
        byte_cnt = self._bytes_needed(bit_len)
        data = bytearray(byte_cnt)
        for i in range(byte_cnt - 1, -1, -1):
            data[i] = num & 0xFF
            num >>= 8

        if bit_len <= 28:
            mask = 0xF0 << (4 - byte_cnt)
            data[0] &= ~mask
            mask = (mask << 1) & 0xFF
            data[0] |= mask
        else:
            data[0] = 0xF0 | (byte_cnt - 5)

        for i in range(0, byte_cnt):
            self._write(data[i])

    def write_meta(self, meta: SHVMetaType) -> None:  # noqa: D102
        self._write(ChainPack.Schema.CP_MetaMap)
        for k, v in meta.items():
            self.write(k)
            self.write(v)
        self._write(ChainPack.Schema.CP_TERM)

    def write_null(self) -> None:  # noqa: D102
        self._write(ChainPack.Schema.CP_Null)

    def write_bool(self, value: bool) -> None:  # noqa: D102
        self._write(ChainPack.Schema.CP_TRUE if value else ChainPack.Schema.CP_FALSE)

    def write_blob(self, value: bytes | bytearray) -> None:  # noqa: D102
        self._write(ChainPack.Schema.CP_Blob)
        self.write_uint_data(len(value))
        self._write(value)

    def write_string(self, value: str) -> None:  # noqa: D102
        bstring = value.encode("utf-8")
        self._write(ChainPack.Schema.CP_String)
        self.write_uint_data(len(bstring))
        self._write(bstring)

    def write_cstring(self, value: str) -> None:  # noqa: D102
        bstring = value.encode("utf-8")
        self._write(ChainPack.Schema.CP_CString)
        self._write(bstring)
        self._write(b"\0")

    def write_uint(self, value: int) -> None:  # noqa: D102
        if value < 64:
            self._write(value % 64)
        else:
            self._write(ChainPack.Schema.CP_UInt)
            self.write_uint_data(value)

    def write_uint_data(self, value: int) -> None:  # noqa: D102
        bitcnt = value.bit_length()
        self._write_uint_data_helper(value, bitcnt)

    def write_int(self, value: int) -> None:  # noqa: D102
        if 0 <= value < 64:
            self._write((value % 64) + 64)
        else:
            self._write(ChainPack.Schema.CP_Int)
            self.write_int_data(value)

    def write_int_data(self, value: int) -> None:  # noqa: D102
        num: int = abs(value)
        neg: bool = value < 0

        bitlen = num.bit_length()
        bitlen += 1  # add sign bit
        if neg:
            sign_pos = self._expand_bit_len(bitlen)
            sign_bit_mask = 1 << sign_pos
            num |= sign_bit_mask
        self._write_uint_data_helper(num, bitlen)

    def write_double(self, value: float) -> None:  # noqa: D102
        self._write(ChainPack.Schema.CP_Double)
        self._write(struct.pack("<d", value))  # little endian

    def write_decimal(self, value: decimal.Decimal) -> None:  # noqa: D102
        mantissa, exponent = decimal_rexp(value)
        self._write(ChainPack.Schema.CP_Decimal)
        self.write_int_data(mantissa)
        self.write_int_data(exponent)

    def write_list(self, value: SHVListType) -> None:  # noqa: D102
        self._write(ChainPack.Schema.CP_List)
        for val in value:
            self.write(val)
        self._write(ChainPack.Schema.CP_TERM)

    def write_map(self, value: SHVMapType) -> None:  # noqa: D102
        self._write(ChainPack.Schema.CP_Map)
        for k, v in value.items():
            self.write(k)
            self.write(v)
        self._write(ChainPack.Schema.CP_TERM)

    def write_imap(self, value: SHVIMapType) -> None:  # noqa: D102
        self._write(ChainPack.Schema.CP_IMap)
        for k, v in value.items():
            self.write(k)
            self.write(v)
        self._write(ChainPack.Schema.CP_TERM)

    def write_datetime(self, value: datetime.datetime) -> None:  # noqa: D102
        self._write(ChainPack.Schema.CP_DateTime)
        res = int(value.timestamp() * 1000) - (ChainPack.SHV_EPOCH_SEC * 1000)
        tzdelta = value.utcoffset()
        tzoff = int(tzdelta.total_seconds() // 60 // 15) if tzdelta is not None else 0
        if not -63 <= tzoff <= 63:
            raise ValueError(f"Invalid UTC offset value: {tzoff}")
        ms = res % 1000 == 0
        if ms:
            res //= 1000
        if tzoff != 0:
            res <<= 7
            res |= tzoff & 0x7F
        res <<= 2
        if tzoff != 0:
            res |= 1
        if ms:
            res |= 2
        self.write_int_data(res)
