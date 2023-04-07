import struct
import sys

from .cpcontext import PackContext, UnpackContext
from .rpcvalue import RpcValue


class ChainPack:
    def __init__(self):
        pass

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
    SHV_EPOCH_MSEC = 1517529600000
    # ChainPack.INVALID_MIN_OFFSET_FROM_UTC = (-64 * 15)

    @staticmethod
    def is_little_endian():
        return sys.byteorder == "little"


class ChainPackReader:
    def __init__(self, unpack_context):
        if isinstance(unpack_context, (bytes, bytearray)):
            unpack_context = UnpackContext(unpack_context)
        self.ctx = unpack_context

    def read(self):
        rpc_val = RpcValue()
        packing_schema = self.ctx.get_byte()

        if packing_schema == ChainPack.CP_MetaMap:
            rpc_val.meta = self._read_map()
            packing_schema = self.ctx.get_byte()

        if packing_schema < 128:
            if packing_schema & 64:
                # tiny Int
                rpc_val.type = RpcValue.Type.Int
                rpc_val.value = packing_schema & 63
            else:
                # tiny UInt
                rpc_val.type = RpcValue.Type.UInt
                rpc_val.value = packing_schema & 63
        else:
            if packing_schema == ChainPack.CP_Null:
                rpc_val.type = RpcValue.Type.Null
                rpc_val.value = None
            elif packing_schema == ChainPack.CP_TRUE:
                rpc_val.type = RpcValue.Type.Bool
                rpc_val.value = True

            elif packing_schema == ChainPack.CP_FALSE:
                rpc_val.type = RpcValue.Type.Bool
                rpc_val.value = False

            elif packing_schema == ChainPack.CP_Int:
                rpc_val.value = self._read_int_data()
                rpc_val.type = RpcValue.Type.Int
            elif packing_schema == ChainPack.CP_UInt:
                rpc_val.value = self.read_uint_data()
                rpc_val.type = RpcValue.Type.UInt
            elif packing_schema == ChainPack.CP_Double:
                data = bytearray(8)
                for i in range(8):
                    data[i] = self.ctx.get_byte()
                rpc_val.value = struct.unpack("<d", data)  # little endian
                rpc_val.type = RpcValue.Type.Double
            elif packing_schema == ChainPack.CP_Decimal:
                mant = self._read_int_data()
                exp = self._read_int_data()
                rpc_val.value = RpcValue.Decimal(mant, exp)
                rpc_val.type = RpcValue.Type.Decimal
            elif packing_schema == ChainPack.CP_DateTime:
                d = self.read_uint_data()
                offset = 0
                has_tz_offset = d & 1
                has_not_msec = d & 2
                d >>= 2
                if has_tz_offset:
                    offset = d & 0x7F
                    if offset & 0b01000000:
                        offset = offset - 128  # sign extension
                    d >>= 7
                if has_not_msec:
                    d *= 1000
                d += ChainPack.SHV_EPOCH_MSEC
                rpc_val.value = RpcValue.DateTime(d, offset * 15)
                rpc_val.type = RpcValue.Type.DateTime

            elif packing_schema == ChainPack.CP_Map:
                rpc_val.value = self._read_map()
                rpc_val.type = RpcValue.Type.Map

            elif packing_schema == ChainPack.CP_IMap:
                rpc_val.value = self._read_map()
                rpc_val.type = RpcValue.Type.IMap

            elif packing_schema == ChainPack.CP_List:
                rpc_val.value = self._read_list()
                rpc_val.type = RpcValue.Type.List

            elif packing_schema == ChainPack.CP_Blob:
                str_len = self.read_uint_data()
                arr = bytearray(str_len)
                for i in range(str_len):
                    arr[i] = self.ctx.get_byte()
                rpc_val.value = bytes(arr)
                rpc_val.type = RpcValue.Type.Blob

            elif packing_schema == ChainPack.CP_String:
                str_len = self.read_uint_data()
                arr = bytearray(str_len)
                for i in range(str_len):
                    arr[i] = self.ctx.get_byte()
                rpc_val.value = bytes(arr).decode()
                rpc_val.type = RpcValue.Type.String

            elif packing_schema == ChainPack.CP_CString:
                # variation of CponReader.readCString()
                pctx = PackContext()
                while True:
                    b = self.ctx.get_byte()
                    if b == ord("\\"):
                        b = self.ctx.get_byte()
                        if b == ord("\\"):
                            pctx.put_byte(ord("\\"))
                        elif b == ord("0"):
                            pctx.put_byte(0)
                        else:
                            pctx.put_byte(b)
                    else:
                        if b == 0:
                            break  # end of string
                        else:
                            pctx.put_byte(b)
                rpc_val.value = pctx.data_bytes()
                rpc_val.type = RpcValue.Type.String
            else:
                raise TypeError("ChainPack - Invalid type info: " + packing_schema)
        return rpc_val

    @classmethod
    def unpack(cls, chainpack):
        if isinstance(chainpack, (bytes, bytearray)):
            rd = ChainPackReader(UnpackContext(chainpack))
        else:
            raise TypeError("Unsupported type: " + type(chainpack))
        return rd.read()

    def _read_uint_dataHelper(self):
        num = 0
        bitlen = 0
        head = self.ctx.get_byte()
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

        for i in range(bytes_to_read_cnt):
            r = self.ctx.get_byte()
            num = (num << 8) + r
        return num, bitlen

    def read_uint_data(self):
        num, bitlen = self._read_uint_dataHelper()
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

    def _read_list(self):
        lst = []
        while True:
            b = self.ctx.peek_byte()
            if b == ChainPack.CP_TERM:
                self.ctx.get_byte()
                break
            item = self.read()
            lst.append(item)
        return lst

    def _read_map(self):
        mmap = {}
        while True:
            b = self.ctx.peek_byte()
            if b == ChainPack.CP_TERM:
                self.ctx.get_byte()
                break
            key = self.read()
            # if !key)
            #    raise TypeError("Malformed map, invalid key")
            val = self.read()
            if key.type == RpcValue.Type.String:
                mmap[key.value] = val
            else:
                mmap[int(key.value)] = val
        return mmap


class ChainPackWriter:
    def __init__(self):
        self.ctx = PackContext()

    def write(self, rpc_val):
        if not isinstance(rpc_val, RpcValue):
            rpc_val = RpcValue(rpc_val)
        if isinstance(rpc_val.meta, dict):
            self.write_meta(rpc_val.meta)
        if rpc_val.type == RpcValue.Type.Undefined:
            # better to write null than create invalid chain-pack
            self.ctx.put_byte(ChainPack.CP_Null)
        if rpc_val.type == RpcValue.Type.Null:
            self.ctx.put_byte(ChainPack.CP_Null)
        elif rpc_val.type == RpcValue.Type.Bool:
            self.ctx.put_byte(
                ChainPack.CP_TRUE if rpc_val.value else ChainPack.CP_FALSE
            )
        elif rpc_val.type == RpcValue.Type.Blob:
            self.write_blob(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.String:
            self.write_string(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.UInt:
            self.write_uint(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.Int:
            self.write_int(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.Double:
            self.write_double(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.Decimal:
            self.write_decimal(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.List:
            self.write_list(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.Map:
            self.write_map(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.IMap:
            self.write_imap(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.DateTime:
            self.write_datetime(rpc_val.value)
        else:
            raise ValueError("Cannot pack invalid RpcValue type.")

    def data_bytes(self):
        return self.ctx.data_bytes()

    @classmethod
    def pack(cls, rpc_val):
        wr = cls()
        wr.write(rpc_val)
        return wr.ctx.data_bytes()

    # // see https://en.wikipedia.org/wiki/Find_first_set#CLZ
    sig_table_4bit = [0, 1, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4]

    @staticmethod
    def _significant_bits_part_length(num):
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
        length += ChainPackWriter.sig_table_4bit[num]
        return max(length, 1)

    #  0 ...  7 bits  1  byte  |0|s|x|x|x|x|x|x|<-- LSB
    #  8 ... 14 bits  2  bytes |1|0|s|x|x|x|x|x| |x|x|x|x|x|x|x|x|<-- LSB
    # 15 ... 21 bits  3  bytes |1|1|0|s|x|x|x|x| |x|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x|<-- LSB
    # 22 ... 28 bits  4  bytes |1|1|1|0|s|x|x|x| |x|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x|<-- LSB
    # 29+       bits  5+ bytes |1|1|1|1|n|n|n|n| |s|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x| |x|x|x|x|x|x|x|x| ... <-- LSB
    #                                         n ==  0 ->  4 bytes number (32 bit number)
    #                                         n ==  1 ->  5 bytes number
    #                                         n == 14 -> 18 bytes number
    #                                         n == 15 -> for future (number of bytes will be specified in next byte)

    # return max bit length >= bit_len, which can be encoded by same number of bytes
    # number of bytes needed to encode bit_len
    @classmethod
    def _bytes_needed(cls, bit_len):
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
            self.ctx.put_byte(r)

    def write_uint_data(self, num):
        bitcnt = self._significant_bits_part_length(num)
        self._write_uint_data_helper(num, bitcnt)

    def write_int_data(self, snum):
        num = -snum if snum < 0 else snum
        neg = snum < 0

        bitlen = self._significant_bits_part_length(num)
        bitlen += 1  # add sign bit
        if neg:
            sign_pos = self._expand_bit_len(bitlen)
            sign_bit_mask = 1 << sign_pos
            num |= sign_bit_mask
        self._write_uint_data_helper(num, bitlen)

    def write_uint(self, n):
        if n < 64:
            self.ctx.put_byte(n % 64)
        else:
            self.ctx.put_byte(ChainPack.CP_UInt)
            self.write_uint_data(n)

    def write_int(self, n):
        if 0 <= n < 64:
            self.ctx.put_byte((n % 64) + 64)
        else:
            self.ctx.put_byte(ChainPack.CP_Int)
            self.write_int_data(n)

    def write_decimal(self, val):
        self.ctx.put_byte(ChainPack.CP_Decimal)
        self.write_int_data(val.mantisa)
        self.write_int_data(val.exponent)

    def write_double(self, val: float):
        self.ctx.put_byte(ChainPack.CP_Double)
        data = struct.pack("<d", val)  # little endian
        self.ctx.write_bytes(data)

    def write_list(self, lst):
        self.ctx.put_byte(ChainPack.CP_List)
        for i in range(0, len(lst)):
            self.write(lst[i])
        self.ctx.put_byte(ChainPack.CP_TERM)

    def write_map_data(self, mmap):
        for k, v in mmap.items():
            self.write(k)
            self.write(v)
        self.ctx.put_byte(ChainPack.CP_TERM)

    def write_map(self, mmap):
        self.ctx.put_byte(ChainPack.CP_Map)
        self.write_map_data(mmap)

    def write_imap(self, mmap):
        self.ctx.put_byte(ChainPack.CP_IMap)
        self.write_map_data(mmap)

    def write_meta(self, mmap):
        self.ctx.put_byte(ChainPack.CP_MetaMap)
        self.write_map_data(mmap)

    def write_blob(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Unsupported type: " + type(data))
        self.ctx.put_byte(ChainPack.CP_Blob)
        self.write_uint_data(len(data))
        for b in data:
            self.ctx.put_byte(b)

    def write_string(self, sstr):
        if not isinstance(sstr, str):
            raise TypeError("Unsupported type: " + type(sstr))
        sstr = sstr.encode()
        self.ctx.put_byte(ChainPack.CP_String)
        self.write_uint_data(len(sstr))
        for b in sstr:
            self.ctx.put_byte(b)

    def write_datetime(self, dt):
        self.ctx.put_byte(ChainPack.CP_DateTime)

        msecs = dt.epochMsec - ChainPack.SHV_EPOCH_MSEC
        offset = dt.utcOffsetMin // 15
        if not (-63 <= offset <= 63):
            raise TypeError("Invalid UTC offset value: " + offset)
        # if offset < 0:
        #     offset = 128 + offset
        offset &= 0x7F
        ms = msecs % 1000
        if ms == 0:
            msecs //= 1000
        if offset != 0:
            msecs <<= 7
            msecs |= offset
        msecs <<= 2
        if offset != 0:
            msecs |= 1
        if ms == 0:
            msecs |= 2
        self.write_int_data(msecs)
