"""Chainpack data format reader and writer."""
import collections.abc
import datetime
import decimal
import functools
import struct

from . import commonpack
from .value import SHVMeta, SHVMetaType, SHVType, SHVUInt


class ChainPack:
    """ChainPack constans and definitions."""

    ProtocolType = 1

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

    @classmethod
    def unpack(cls, data: bytes | str) -> SHVType:
        """Unpack single value from given data."""
        return ChainPackReader.unpack(data)

    @classmethod
    def pack(cls, value: SHVType) -> bytes:
        """Pack given value and return bytes."""
        return ChainPackWriter.pack(value)


class ChainPackReader(commonpack.CommonReader):
    """Read data in ChainPack format."""

    def read_meta(self) -> SHVMetaType | None:
        if self._peek_byte() != ChainPack.CP_MetaMap:
            return None
        self._read_byte()
        return self._read_map()

    def read(self) -> SHVType:
        meta = self.read_meta()

        value: SHVType
        packing_schema = self._read_byte()
        if packing_schema < 128:
            # tiny Int or UInt
            value = packing_schema & 63
            if not packing_schema & 64:
                value = SHVUInt(value)
        elif packing_schema == ChainPack.CP_Null:
            value = None
        elif packing_schema == ChainPack.CP_TRUE:
            value = True
        elif packing_schema == ChainPack.CP_FALSE:
            value = False
        elif packing_schema == ChainPack.CP_Int:
            value = self._read_int_data()
        elif packing_schema == ChainPack.CP_UInt:
            value = SHVUInt(self.read_uint_data())
        elif packing_schema == ChainPack.CP_Double:
            value = self._read_double()
        elif packing_schema == ChainPack.CP_Decimal:
            value = self._read_decimal()
        elif packing_schema == ChainPack.CP_DateTime:
            value = self._read_datetime()
        elif packing_schema == ChainPack.CP_Map:
            value = self._read_map()
        elif packing_schema == ChainPack.CP_IMap:
            value = self._read_map()
        elif packing_schema == ChainPack.CP_List:
            value = self._read_list()
        elif packing_schema == ChainPack.CP_Blob:
            value = self._read_blob()
        elif packing_schema == ChainPack.CP_String:
            value = self._read_string()
        elif packing_schema == ChainPack.CP_CString:
            value = self._read_cstring()
        else:
            raise TypeError(f"ChainPack - Invalid type: {packing_schema}")
        if meta is not None:
            value = SHVMeta.new(value, meta)
        return value

    def _read_uint_dataHelper(self):
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

    def read_uint_data(self):
        num, _ = self._read_uint_dataHelper()
        return num

    def _read_int_data(self):
        num, bitlen = self._read_uint_dataHelper()
        sign_bit_mask = 1 << (bitlen - 1)
        neg = num & sign_bit_mask
        snum = num
        if neg:
            snum &= ~sign_bit_mask
            snum = -snum
        return snum

    def _read_double(self) -> float:
        res = struct.unpack("<d", self._read(8))  # little endian
        return res[0]

    def _read_decimal(self):
        mant = self._read_int_data()
        exp = self._read_int_data()
        return decimal.Decimal(f"{mant}e{exp}")

    def _read_datetime(self):
        d = self.read_uint_data()
        offset = 0
        has_tz_offset = d & 1
        has_not_msec = d & 2
        d >>= 2
        if has_tz_offset:
            offset = d & 0x7F
            if offset >= 128:
                offset -= 128  # sign extension
            d >>= 7
        if not has_not_msec:
            d /= 1000
        d += ChainPack.SHV_EPOCH_SEC
        tzone = datetime.timezone(datetime.timedelta(minutes=offset * 15))
        return datetime.datetime.fromtimestamp(d, tzone)

    def _read_blob(self) -> bytes:
        dlen = self.read_uint_data()
        return self._read(dlen)

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

    def _read_list(self):
        lst = []
        while True:
            b = self._peek_byte()
            if b == ChainPack.CP_TERM:
                self._read_byte()
                break
            lst.append(self.read())
        return lst

    def _read_map(self):
        mmap = {}
        while True:
            b = self._peek_byte()
            if b == ChainPack.CP_TERM:
                self._read_byte()
                break
            key = self.read()
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

    @staticmethod
    def _significant_bits_part_length(num: int) -> int:
        length = 0
        if num & 0xFFFFFFFF00000000:
            length += 32
            num >>= 32
        if num & 0xFFFF0000:
            length += 16
            num >>= 16
        if num & 0xFF00:
            length += 8
            num >>= 8
        if num & 0xF0:
            length += 4
            num >>= 4
        # see https://en.wikipedia.org/wiki/Find_first_set#CLZ
        sig_table_4bit = [0, 1, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4]
        length += sig_table_4bit[num]
        return max(length, 1)

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
        return cnt

    @classmethod
    def _expand_bit_len(cls, bit_len):
        byte_cnt = cls._bytes_needed(bit_len)
        if bit_len <= 28:
            ret = byte_cnt * (8 - 1) - 1
        else:
            ret = (byte_cnt - 1) * 8 - 1
        return ret

    def _write_uint_data_helper(self, num, bit_len):
        byte_cnt = self._bytes_needed(bit_len)
        data = bytearray(byte_cnt)
        for i in range(byte_cnt - 1, -1, -1):
            r = num & 255
            data[i] = r
            num = num >> 8

        if bit_len <= 28:
            mask = 0xF0 << (4 - byte_cnt)
            data[0] = data[0] & ~mask
            mask = (mask << 1) & 0xFF
            data[0] = data[0] | mask
        else:
            data[0] = 0xF0 | (byte_cnt - 5)

        for i in range(0, byte_cnt):
            r = data[i]
            self._write(r)

    def write_meta(self, meta: dict) -> None:
        self._write(ChainPack.CP_MetaMap)
        self._write_map_data(meta)

    def write_null(self) -> None:
        self._write(ChainPack.CP_Null)

    def write_bool(self, value: bool) -> None:
        self._write(ChainPack.CP_TRUE if value else ChainPack.CP_FALSE)

    def write_blob(self, value: bytes | bytearray) -> None:
        self._write(ChainPack.CP_Blob)
        self.write_uint_data(len(value))
        self._write(value)

    def write_string(self, value: str) -> None:
        bstring = value.encode("utf-8")
        self._write(ChainPack.CP_String)
        self.write_uint_data(len(bstring))
        self._write(bstring)

    def write_cstring(self, value: str) -> None:
        bstring = value.encode("utf-8")
        self._write(ChainPack.CP_CString)
        self._write(bstring)
        self._write(b"\0")

    def write_uint(self, value: int) -> None:
        if value < 64:
            self._write(value % 64)
        else:
            self._write(ChainPack.CP_UInt)
            self.write_uint_data(value)

    def write_uint_data(self, value: int) -> None:
        bitcnt = self._significant_bits_part_length(value)
        self._write_uint_data_helper(value, bitcnt)

    def write_int(self, value: int) -> None:
        if 0 <= value < 64:
            self._write((value % 64) + 64)
        else:
            self._write(ChainPack.CP_Int)
            self.write_int_data(value)

    def write_int_data(self, value: int) -> None:
        num = -value if value < 0 else value
        neg = value < 0

        bitlen = self._significant_bits_part_length(num)
        bitlen += 1  # add sign bit
        if neg:
            sign_pos = self._expand_bit_len(bitlen)
            sign_bit_mask = 1 << sign_pos
            num |= sign_bit_mask
        self._write_uint_data_helper(num, bitlen)

    def write_double(self, value: float) -> None:
        self._write(ChainPack.CP_Double)
        self._write(struct.pack("<d", value))  # little endian

    def write_decimal(self, value: decimal.Decimal) -> None:
        t = value.as_tuple()
        mantisa = functools.reduce(
            lambda a, b: a + (b[1] * 10 ** b[0]), enumerate(reversed(t.digits)), 0
        ) * (-1 if t.sign else 1)
        exponent = t.exponent
        assert isinstance(exponent, int)
        self._write(ChainPack.CP_Decimal)
        self.write_int_data(mantisa)
        self.write_int_data(exponent)

    def write_list(self, value: collections.abc.Iterable[SHVType]) -> None:
        self._write(ChainPack.CP_List)
        for val in value:
            self.write(val)
        self._write(ChainPack.CP_TERM)

    def _write_map_data(self, mmap):
        for k, v in mmap.items():
            self.write(k)
            self.write(v)
        self._write(ChainPack.CP_TERM)

    def write_map(self, value: collections.abc.Mapping[str, SHVType]) -> None:
        self._write(ChainPack.CP_Map)
        self._write_map_data(value)

    def write_imap(self, value: collections.abc.Mapping[int, SHVType]) -> None:
        self._write(ChainPack.CP_IMap)
        self._write_map_data(value)

    def write_datetime(self, value: datetime.datetime) -> None:
        self._write(ChainPack.CP_DateTime)
        res = int(value.timestamp() * 1000) - (ChainPack.SHV_EPOCH_SEC * 1000)
        tzdelta = value.utcoffset()
        tzoff = int(tzdelta.total_seconds() // 60 // 15) if tzdelta is not None else 0
        if not -63 <= tzoff <= 63:
            raise TypeError(f"Invalid UTC offset value: {tzoff}")
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
