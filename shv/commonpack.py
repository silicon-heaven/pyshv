"""Common base for SHV writers and readers."""

from __future__ import annotations

import abc
import asyncio
import collections.abc
import datetime
import decimal
import io
import typing

from .value import (
    SHVIMapType,
    SHVListType,
    SHVMapType,
    SHVMetaType,
    SHVType,
    SHVUInt,
    is_shvbool,
    is_shvimap,
    is_shvmap,
    is_shvnull,
    shvmeta,
)


class CommonReader(abc.ABC):
    """Common reader base."""

    def __init__(self, stream: bytes | bytearray | typing.IO | CommonReader) -> None:
        if isinstance(stream, bytes | bytearray):
            stream = io.BytesIO(stream)
        if isinstance(stream, CommonReader):
            orig = stream
            stream = stream.stream

        self.stream: typing.IO = stream
        """Stream used to receive bytes from."""
        self.peek_byte = b""
        """Peeked byte if any."""
        self.bytes_cnt = 0
        """Number of bytes read so far."""

        if isinstance(stream, CommonReader):
            self.peek_byte = orig.peek_byte
            self.bytes_cnt = orig.bytes_cnt

    def _read(self, size: int) -> bytes:
        """Read bytes from the stream.

        Compared to regular read this reads always given number of bytes.

        :param size: Number of bytes to read.
        :return: Read bytes.
        :raise ValueError: in case no enough data is available.
        """
        assert size > 0
        self.bytes_cnt += size
        res = self.peek_byte
        self.peek_byte = b""
        size -= len(res)
        while size:
            read = self.stream.read(size)
            if not read:
                raise ValueError("Unexpected end of message.")
            res += read
            size -= len(read)
        return res

    def _read_byte(self) -> int:
        """Read a single byte and return it as int.

        :return: Read byte.
        :raise ValueError: in case no enough data is available.
        """
        return self._read(1)[0]

    def _peek_byte(self) -> int:
        """Peek a single byte and return it as int.

        Peeked byte is actually read from the stream and is stored to
        `peek_byte`.

        :return: Peeked byte. This also returns `0` when EOF is encountered.
        Make sure that you use `0` to terminate what you are doing.
        """
        if not self.peek_byte:
            self.peek_byte = self.stream.read(1)
        return self.peek_byte[0] if self.peek_byte else 0

    def _peek_drop(self) -> None:
        """Drop peeked data."""
        self.bytes_cnt += len(self.peek_byte)
        self.peek_byte = b""

    def _read_check(self, data: bytes) -> None:
        """Read bytes and check that it is what we expected.

        :param data: Expected bytes.
        :raise ValueError: when unexpected byte was received or not enough data
          available.
        """
        b = self._read(len(data))
        if data != b:
            raise ValueError(f"Expected {data!r} but got {b!r}")

    @abc.abstractmethod
    def read(self) -> SHVType:
        """Read next SHV value.

        :raise ValueError: when unexpected byte was received.
        """

    @classmethod
    def unpack(cls, data: bytes | str) -> SHVType:
        """Unpack single value from given data."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        self = cls(io.BytesIO(data))
        return self.read()


class CommonWriter(abc.ABC):
    """Common writer base."""

    def __init__(self, stream: typing.IO | asyncio.StreamWriter | None = None) -> None:
        self.stream = stream or io.BytesIO()
        self.bytes_cnt = 0

    def _write(self, data: bytes | int) -> None:
        if isinstance(data, int):
            data = bytes([data])
        self.bytes_cnt += len(data)
        self.stream.write(data)

    def _writestr(self, data: str) -> None:
        self._write(data.encode("utf-8"))

    def write(self, value: SHVType) -> None:
        """Write generic RpcValue."""
        if shvmeta(value):
            self.write_meta(shvmeta(value))
        if is_shvnull(value):
            self.write_null()
        elif is_shvbool(value):
            self.write_bool(bool(value))
        elif isinstance(value, SHVUInt):
            self.write_uint(value)
        elif isinstance(value, int):
            self.write_int(value)
        elif isinstance(value, float):
            self.write_double(value)
        elif isinstance(value, decimal.Decimal):
            self.write_decimal(value)
        elif isinstance(value, bytes):
            self.write_blob(value)
        elif isinstance(value, str):
            self.write_string(value)
        elif isinstance(value, datetime.datetime):
            self.write_datetime(value)
        elif isinstance(value, collections.abc.Sequence):
            self.write_list(value)
        elif is_shvimap(value):
            self.write_imap(value)
        elif is_shvmap(value):
            self.write_map(value)
        else:
            raise ValueError(f"Invalid value for SHV: {value!r}")

    @abc.abstractmethod
    def write_meta(self, meta: SHVMetaType) -> None:
        """Write given meta to the stream."""

    @abc.abstractmethod
    def write_null(self) -> None:
        """Write null to the stream."""

    @abc.abstractmethod
    def write_bool(self, value: bool) -> None:
        """Write boolean to the stream."""

    @abc.abstractmethod
    def write_blob(self, value: bytes | bytearray) -> None:
        """Write blob to the stream."""

    @abc.abstractmethod
    def write_string(self, value: str) -> None:
        """Write string to the stream."""

    @abc.abstractmethod
    def write_cstring(self, value: str) -> None:
        """Write C string to the stream."""

    @abc.abstractmethod
    def write_uint(self, value: int) -> None:
        """Write unsigned integer to the stream."""

    @abc.abstractmethod
    def write_int(self, value: int) -> None:
        """Write signed integer to the stream."""

    @abc.abstractmethod
    def write_double(self, value: float) -> None:
        """Write floating point number to the stream."""

    @abc.abstractmethod
    def write_decimal(self, value: decimal.Decimal) -> None:
        """Write decimal number to the stream."""

    @abc.abstractmethod
    def write_list(self, value: SHVListType) -> None:
        """Write list of other types to the stream."""

    @abc.abstractmethod
    def write_map(self, value: SHVMapType) -> None:
        """Write map of other types to the stream."""

    @abc.abstractmethod
    def write_imap(self, value: SHVIMapType) -> None:
        """Write integer map of other types to the stream."""

    @abc.abstractmethod
    def write_datetime(self, value: datetime.datetime) -> None:
        """Write date and time to the stream."""

    @classmethod
    def pack(cls, value: SHVType) -> bytes:
        """Pack given value and return bytes."""
        stream = io.BytesIO()
        self = cls(stream)
        self.write(value)
        return stream.getvalue()
