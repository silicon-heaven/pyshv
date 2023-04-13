import datetime

from .cpcontext import PackContext, UnpackContext
from .rpcvalue import RpcValue


class Cpon:

    ProtocolType = 2


class CponReader:

    SPACE = ord(" ")
    SLASH = ord("/")
    STAR = ord("*")
    LF = ord("\n")
    KEY_DELIM = ord(":")
    FIELD_DELIM = ord(",")

    def __init__(self, unpack_context):
        # assert type(unpack_context) == UnpackContext
        if isinstance(unpack_context, (bytes, bytearray)):
            unpack_context = UnpackContext(unpack_context)
        self.ctx = unpack_context

    def skip_white_insignificant(self):
        while True:
            b = self.ctx.peek_byte()
            if b < 1:
                return
            if b > CponReader.SPACE:
                if b == CponReader.SLASH:
                    self.ctx.get_byte()
                    b = self.ctx.get_byte()
                    if b == CponReader.STAR:
                        # multiline_comment_entered
                        while True:
                            b = self.ctx.get_byte()
                            if b == CponReader.STAR:
                                b = self.ctx.get_byte()
                                if b == CponReader.SLASH:
                                    break
                    elif b == CponReader.SLASH:
                        # to end of line comment entered
                        while True:
                            b = self.ctx.get_byte()
                            if b == CponReader.LF:
                                break
                    else:
                        raise TypeError("Malformed comment")
                elif b == CponReader.KEY_DELIM:
                    self.ctx.get_byte()
                    continue
                elif b == CponReader.FIELD_DELIM:
                    self.ctx.get_byte()
                    continue
                else:
                    break
            else:
                self.ctx.get_byte()

    def read(self):
        meta = None

        self.skip_white_insignificant()
        b = self.ctx.peek_byte()
        if b == ord("<"):
            meta = self._read_map(">")

        self.skip_white_insignificant()
        b = self.ctx.peek_byte()
        if ord("0") <= b <= ord("9") or b == ord("+") or b == ord("-"):
            value, val_type = self._read_number()
        elif b == ord('"'):
            value = self._read_cstring()
            val_type = RpcValue.Type.String
        elif b == ord("["):
            value = self._read_list()
            val_type = RpcValue.Type.List
        elif b == ord("{"):
            value = self._read_map()
            val_type = RpcValue.Type.Map
        elif b == ord("i"):
            self.ctx.get_byte()
            b = self.ctx.peek_byte()
            if b == ord("{"):
                value = self._read_map()
                val_type = RpcValue.Type.IMap
            else:
                raise TypeError("Invalid IMap prefix.")
        elif b == ord("d"):
            self.ctx.get_byte()
            b = self.ctx.peek_byte()
            if b == ord('"'):
                value = self._read_datetime()
                val_type = RpcValue.Type.DateTime
            else:
                raise TypeError("Invalid DateTime prefix.")
        elif b == ord("b"):
            self.ctx.get_byte()
            b = self.ctx.peek_byte()
            if b == ord('"'):
                value = self._read_blob()
                val_type = RpcValue.Type.Blob
            else:
                raise TypeError("Invalid Blob prefix.")
        elif b == ord("x"):
            self.ctx.get_byte()
            b = self.ctx.peek_byte()
            if b == ord('"'):
                value = self._read_hexblob()
                val_type = RpcValue.Type.Blob
            else:
                raise TypeError("Invalid HexBlob prefix.")
        elif b == ord("t"):
            self.ctx.get_bytes(b"true")
            value = True
            val_type = RpcValue.Type.Bool
        elif b == ord("f"):
            self.ctx.get_bytes(b"false")
            value = False
            val_type = RpcValue.Type.Bool
        elif b == ord("n"):
            self.ctx.get_bytes(b"null")
            value = None
            val_type = RpcValue.Type.Null
        else:
            raise TypeError("Malformed Cpon input.")
        ret = RpcValue(value, meta, val_type)
        return ret

    @classmethod
    def unpack(cls, cpon):
        if isinstance(cpon, str):
            rd = CponReader(UnpackContext(cpon.encode()))
        elif isinstance(cpon, (bytes, bytearray)):
            rd = CponReader(UnpackContext(cpon))
        else:
            raise TypeError("Unsupported type: " + type(cpon))
        return rd.read()

    def _read_datetime(self):
        msec = 0
        utc_offset = 0

        self.ctx.get_byte()  # eat '"'
        b = self.ctx.peek_byte()
        if b == ord('"'):
            # d"" invalid data time
            raise TypeError("Empty date time not supported")

        year = self._read_int()

        b = self.ctx.get_byte()
        if b != ord("-"):
            raise TypeError("Malformed year-month separator in DateTime")
        month = self._read_int()

        b = self.ctx.get_byte()
        if b != ord("-"):
            raise TypeError("Malformed year-month separator in DateTime")
        day = self._read_int()

        b = self.ctx.get_byte()
        if b != ord(" ") and b != ord("T"):
            raise TypeError("Malformed date-time separator in DateTime")
        hour = self._read_int()

        b = self.ctx.get_byte()
        if b != ord(":"):
            raise TypeError("Malformed year-month separator in DateTime")
        mins = self._read_int()

        b = self.ctx.get_byte()
        if b != ord(":"):
            raise TypeError("Malformed year-month separator in DateTime")
        sec = self._read_int()

        b = self.ctx.peek_byte()
        if b == ord("."):
            self.ctx.get_byte()
            msec = self._read_int()

        b = self.ctx.peek_byte()
        if b == ord("Z"):
            # zulu time
            self.ctx.get_byte()
        elif b == ord("+") or b == ord("-"):
            # UTC time offset
            self.ctx.get_byte()
            ix1 = self.ctx.index
            val = self._read_int()
            n = self.ctx.index - ix1
            if not (n == 2 or n == 4):
                raise TypeError("Malformed TS offset in DateTime.")
            if n == 2:
                utc_offset = 60 * val
            elif n == 4:
                utc_offset = 60 * ((val // 100) >> 0) + (val % 100)
            if b == ord("-"):
                utc_offset = -utc_offset

        b = self.ctx.get_byte()
        if b != ord('"'):
            raise TypeError('DateTime literal should be terminated by ".')
        # d = datetime.datetime(year, month, day, hour, min, sec, msec, datetime.timezone.utc)
        d = datetime.datetime(
            year,
            month,
            day,
            hour,
            mins,
            sec,
            msec,
            datetime.timezone(datetime.timedelta(minutes=utc_offset)),
        )
        epoch_msec = int(d.timestamp() * 1000)
        return RpcValue.DateTime(epoch_msec + msec, utc_offset)

    def _hexdigit_to_int(b):
        if ord("0") <= b <= ord("9"):
            val = b - 48
        elif ord("a") <= b <= ord("f"):
            val = b - ord("a") + 10
        elif ord("A") <= b <= ord("F"):
            val = b - ord("A") + 10
        else:
            raise ValueError("Invalid HEX digit: " + b)
        return val

    def _read_blob(self):
        pctx = PackContext()
        self.ctx.get_byte()  # eat '"'
        while True:
            b = self.ctx.get_byte()
            if b == ord("\\"):
                b = self.ctx.get_byte()
                if b == ord("\\"):
                    pctx.put_byte(ord("\\"))
                elif b == ord('"'):
                    pctx.put_byte(ord('"'))
                elif b == ord("n"):
                    pctx.put_byte(ord("\n"))
                elif b == ord("r"):
                    pctx.put_byte(ord("\r"))
                elif b == ord("t"):
                    pctx.put_byte(ord("\t"))
                else:
                    hi = b
                    lo = self.ctx.get_byte()
                    pctx.put_byte(
                        16 * CponReader._hexdigit_to_int(hi)
                        + CponReader._hexdigit_to_int(lo)
                    )
            else:
                if b == ord('"'):
                    # end of string
                    break
                else:
                    pctx.put_byte(b)
        return pctx.data_bytes()

    def _read_hexblob(self):
        pctx = PackContext()
        self.ctx.get_byte()  # eat '"'
        while True:
            b = self.ctx.get_byte()
            if b == ord('"'):
                # end of string
                break
            hi = b
            lo = self.ctx.get_byte()
            pctx.put_byte(
                16 * CponReader._hexdigit_to_int(hi) + CponReader._hexdigit_to_int(lo)
            )
        return pctx.data_bytes()

    def _read_cstring(self):
        pctx = PackContext()
        self.ctx.get_byte()  # eat '"'
        while True:
            b = self.ctx.get_byte()
            if b == ord("\\"):
                b = self.ctx.get_byte()
                if ord("\\"):
                    pctx.put_byte(ord("\\"))
                elif ord("b"):
                    pctx.put_byte(ord("\b"))
                elif ord('"'):
                    pctx.put_byte(ord('"'))
                elif ord("f"):
                    pctx.put_byte(ord("\f"))
                elif ord("n"):
                    pctx.put_byte(ord("\n"))
                elif ord("r"):
                    pctx.put_byte(ord("\r"))
                elif ord("t"):
                    pctx.put_byte(ord("\t"))
                elif ord("0"):
                    pctx.put_byte(0)
                else:
                    pctx.put_byte(b)
            else:
                if b == ord('"'):
                    # end of string
                    break
                else:
                    pctx.put_byte(b)
        return pctx.data_bytes().decode()

    def _read_list(self):
        lst = []
        self.ctx.get_byte()  # eat '['
        while True:
            self.skip_white_insignificant()
            b = self.ctx.peek_byte()
            if b == ord("]"):
                self.ctx.get_byte()
                break
            item = self.read()
            lst.append(item)
        return lst

    def _read_map(self, terminator="}"):
        mmap = {}
        self.ctx.get_byte()  # eat '{'
        while True:
            self.skip_white_insignificant()
            b = self.ctx.peek_byte()
            if b == ord(terminator):
                self.ctx.get_byte()
                break
            key = self.read()
            if key.type == RpcValue.Type.String:
                key = key.value
            elif key.type == RpcValue.Type.UInt:
                key = key.value
            elif key.type == RpcValue.Type.Int:
                key = key.value
            else:
                raise TypeError("Malformed map, invalid key")
            self.skip_white_insignificant()
            val = self.read()
            mmap[key] = val
        return mmap

    def _read_int(self):
        base = 10
        val = 0
        neg = False
        n = -1
        while True:
            n += 1
            b = self.ctx.peek_byte()
            if b < 0:
                break
            if b == ord("+") or b == ord("-"):  # '+','-'
                if n > 0:
                    break
                self.ctx.get_byte()
                if b == ord("-"):
                    neg = True
            elif b == ord("x"):
                if n == 1 and val != 0:
                    break
                if n != 1:
                    break
                self.ctx.get_byte()
                base = 16
            elif ord("0") <= b <= ord("9"):
                self.ctx.get_byte()
                val *= base
                val += b - 48
            elif ord("A") <= b <= ord("F"):
                if base != 16:
                    break
                self.ctx.get_byte()
                val *= base
                val += b - ord("A") + 10
            elif ord("a") <= b <= ord("f"):
                if base != 16:
                    break
                self.ctx.get_byte()
                val *= base
                val += b - ord("a") + 10
            else:
                break

        if neg:
            val = -val
        return val

    def _read_number(self):
        # mantisa = 0
        exponent = 0
        decimals = 0
        dec_cnt = 0
        is_decimal = False
        is_uint = False
        is_neg = False

        # val_type = RpcValue.Type.Undefined
        # value = None

        b = self.ctx.peek_byte()
        if b == ord("+"):
            is_neg = False
        elif b == ord("-"):
            is_neg = True
            self.ctx.get_byte()

        mantisa = self._read_int()
        b = self.ctx.peek_byte()
        while b > 0:
            if b == ord("u"):
                is_uint = 1
                self.ctx.get_byte()
                break
            if b == ord("."):
                is_decimal = 1
                self.ctx.get_byte()
                ix1 = self.ctx.index
                decimals = self._read_int()
                dec_cnt = self.ctx.index - ix1
                b = self.ctx.peek_byte()
                if b < 0:
                    break
            if b == ord("e") or b == ord("E"):
                is_decimal = 1
                self.ctx.get_byte()
                ix1 = self.ctx.index
                exponent = self._read_int()
                if ix1 == self.ctx.index:
                    raise TypeError("Malformed number exponential part.")
                break
            break
        if is_decimal:
            for i in range(dec_cnt):
                mantisa *= 10
            mantisa += decimals
            val_type = RpcValue.Type.Decimal
            value = RpcValue.Decimal(
                -mantisa if is_neg else mantisa, exponent - dec_cnt
            )
        elif is_uint:
            val_type = RpcValue.Type.UInt
            value = mantisa
        else:
            val_type = RpcValue.Type.Int
            value = -mantisa if is_neg else mantisa
        return value, val_type


class CponWriter:
    class Options:
        def __init__(self, indent=None):
            self.indent = indent.encode() if isinstance(indent, str) else indent

    def __init__(self, options=Options()):
        self.ctx = PackContext()
        self.options = options
        self._nest_level = 0

    def write(self, rpc_val):
        if not isinstance(rpc_val, RpcValue):
            rpc_val = RpcValue(rpc_val)
        if rpc_val.meta is not None:
            self._write_meta(rpc_val.meta)

        if rpc_val.type == RpcValue.Type.Null:
            self.ctx.write_utf8_string("null")
        elif rpc_val.type == RpcValue.Type.Undefined:
            self.ctx.write_utf8_string("null")
        elif rpc_val.type == RpcValue.Type.Bool:
            self._write_bool(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.Blob:
            self._write_blob(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.String:
            self._write_cstring(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.UInt:
            self._write_uint(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.Int:
            self._write_int(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.Double:
            self._write_double(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.Decimal:
            self._write_decimal(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.List:
            self._write_list(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.Map:
            self._write_map(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.IMap:
            self._write_imap(rpc_val.value)
        elif rpc_val.type == RpcValue.Type.DateTime:
            self._write_datetime(rpc_val.value)

    def data_bytes(self):
        return self.ctx.data_bytes()

    @classmethod
    def pack(cls, rpc_val):
        wr = cls()
        wr.write(rpc_val)
        return wr.ctx.data_bytes()

    def _indent_item(self, is_online_container, item_index):
        if not self.options.indent:
            return
        if is_online_container:
            if item_index > 0:
                self.ctx.put_byte(ord(" "))
        else:
            self.ctx.put_byte(ord("\n"))
            s = self.options.indent * self._nest_level
            self.ctx.write_bytes(s)

    def _nibble_to_hexdigit(b):
        if b >= 0:
            if b < 10:
                return b + ord("0")
            elif b < 16:
                return b - 10 + ord("a")
        raise ValueError("Invalid nibble value: " + b)

    def _write_blob(self, data):
        self.ctx.write_utf8_string('b"')
        for b in data:
            if b == ord("\\"):
                self.ctx.write_utf8_string("\\\\")
            elif b == ord("\t"):
                self.ctx.write_utf8_string("\\t")
            elif b == ord("\r"):
                self.ctx.write_utf8_string("\\r")
            elif b == ord("\n"):
                self.ctx.write_utf8_string("\\n")
            elif b == ord('"'):
                self.ctx.write_utf8_string('\\"')
            elif b >= 0x7F:
                self.ctx.write_utf8_string("\\")
                self.ctx.put_byte(CponWriter._nibble_to_hexdigit(b // 16))
                self.ctx.put_byte(CponWriter._nibble_to_hexdigit(b % 16))
            else:
                self.ctx.put_byte(b)
        self.ctx.put_byte(ord('"'))

    def _write_cstring(self, cstr):
        self.ctx.put_byte(ord('"'))
        cstr = cstr.encode()
        for b in cstr:
            if b == 0:
                self.ctx.write_utf8_string("\\0")
            elif b == ord("\\"):
                self.ctx.write_utf8_string("\\\\")
            elif b == ord("\t"):
                self.ctx.write_utf8_string("\\t")
            elif b == ord("\b"):
                self.ctx.write_utf8_string("\\b")
            elif b == ord("\r"):
                self.ctx.write_utf8_string("\\r")
            elif b == ord("\n"):
                self.ctx.write_utf8_string("\\n")
            elif b == ord('"'):
                self.ctx.write_utf8_string('\\"')
            else:
                self.ctx.put_byte(b)
        self.ctx.put_byte(ord('"'))

    def _write_datetime(self, dt):
        if not isinstance(dt, RpcValue.DateTime):
            raise TypeError("Not DateTime")
        epoch_sec = dt.epochMsec / 1000
        utc_offset = dt.utcOffsetMin
        tz = datetime.timezone(datetime.timedelta(minutes=utc_offset))
        dt = datetime.datetime.fromtimestamp(epoch_sec, tz)
        self.ctx.write_utf8_string('d"')
        DT_LEN = 19
        dt_str = dt.isoformat()
        self.ctx.write_utf8_string(dt_str[:DT_LEN])
        dt_str = dt_str[DT_LEN:]
        if len(dt_str) > 0 and dt_str[0] == ".":
            self.ctx.write_utf8_string(dt_str[:4])
            dt_str = dt_str[7:]
        if dt_str[:6] == "+00:00":
            self.ctx.put_byte(ord("Z"))
        elif dt_str[:1] == "Z":
            self.ctx.write_utf8_string(dt_str)
        elif dt_str[:1] == "+" or dt_str[:1] == "-":
            self.ctx.write_utf8_string(dt_str[:3])
            min_part = dt_str[4:6]
            if min_part != "00":
                self.ctx.write_utf8_string(min_part)
        self.ctx.put_byte(ord('"'))

    def _write_bool(self, b):
        self.ctx.write_utf8_string("true" if b else "false")

    def _write_meta(self, mmap):
        self.ctx.put_byte(ord("<"))
        self._write_map_content(mmap)
        self.ctx.put_byte(ord(">"))

    def _write_imap(self, mmap):
        self.ctx.write_utf8_string("i{")
        self._write_map_content(mmap)
        self.ctx.put_byte(ord("}"))

    def _write_map(self, mmap):
        self.ctx.put_byte(ord("{"))
        self._write_map_content(mmap)
        self.ctx.put_byte(ord("}"))

    @staticmethod
    def _is_oneline_map(mmap):
        if len(mmap) > 10:
            return False
        for k, v in mmap.items():
            if isinstance(v, RpcValue):
                if v.type in (
                    RpcValue.Type.Map,
                    RpcValue.Type.IMap,
                    RpcValue.Type.List,
                ):
                    return False
        return True

    def _write_map_content(self, mmap):
        self._nest_level += 1
        is_oneliner = CponWriter._is_oneline_map(mmap)
        int_keys = []
        string_keys = []
        for k in mmap.keys():
            if isinstance(k, int):
                int_keys.append(k)
            else:
                string_keys.append(k)
        int_keys = sorted(int_keys)
        string_keys = sorted(string_keys)
        i = -1
        for k in int_keys:
            v = mmap[k]
            i += 1
            if i > 0:
                self.ctx.put_byte(ord(","))
            self._indent_item(is_oneliner, i)
            self._write_int(k)
            self.ctx.put_byte(ord(":"))
            self.write(v)
        for k in string_keys:
            v = mmap[k]
            i += 1
            if i > 0:
                self.ctx.put_byte(ord(","))
            self._indent_item(is_oneliner, i)
            self.ctx.put_byte(ord('"'))
            self.ctx.write_utf8_string(k)
            self.ctx.put_byte(ord('"'))
            self.ctx.put_byte(ord(":"))
            self.write(v)
        self._nest_level -= 1
        self._indent_item(is_oneliner, 0)

    @staticmethod
    def _is_online_list(lst):
        if len(lst) > 10:
            return False
        for item in lst:
            if item.type in (RpcValue.Type.Map, RpcValue.Type.IMap, RpcValue.Type.List):
                return False
        return True

    def _write_list(self, lst):
        self._nest_level += 1
        is_oneliner = CponWriter._is_online_list(lst)
        self.ctx.put_byte(ord("["))
        for i in range(len(lst)):
            if i > 0:
                self.ctx.put_byte(ord(","))
            self._indent_item(is_oneliner, i)
            self.write(lst[i])
        self._nest_level -= 1
        self._indent_item(is_oneliner, 0)
        self.ctx.put_byte(ord("]"))

    def _write_uint(self, num):
        s = repr(num)
        self.ctx.write_utf8_string(s)
        self.ctx.put_byte(ord("u"))

    def _write_int(self, num):
        s = str(num)
        self.ctx.write_utf8_string(s)

    def _write_double(self, num):
        s = str(num)
        self.ctx.write_utf8_string(s)

    def _write_decimal(self, val):
        mantisa = val.mantisa
        exponent = val.exponent
        if mantisa < 0:
            mantisa = -mantisa
            self.ctx.put_byte(ord("-"))
        mstr = str(mantisa)
        n = len(mstr)
        dec_places = -exponent
        if 0 < dec_places < n:
            dot_ix = n - dec_places
            mstr = mstr[0:dot_ix] + "." + mstr[dot_ix:]
        elif 0 < dec_places <= 3:
            extra_0_cnt = dec_places - n
            str0 = "0."
            for i in range(extra_0_cnt):
                str0 += "0"
            mstr = str0 + mstr
        elif dec_places < 0 and n + exponent <= 9:
            for i in range(exponent):
                mstr += "0"
            mstr += "."
        elif dec_places == 0:
            mstr += "."
        else:
            mstr += "e" + str(exponent)
        self.ctx.write_utf8_string(mstr)
