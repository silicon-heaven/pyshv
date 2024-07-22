"""RPC File access and implementation utility."""

from __future__ import annotations

import binascii
import collections
import dataclasses
import datetime
import enum
import hashlib
import io
import pathlib
import types

from .rpcerror import RpcInvalidParamsError
from .rpcmethod import RpcMethodAccess, RpcMethodDesc, RpcMethodFlags
from .rpcparams import shvargt, shvgett, shvt
from .simplebase import SimpleBase
from .value import SHVType, is_shvimap


@dataclasses.dataclass
class RpcFileStat:
    """The stat information for the RPC File."""

    size: int
    """Size of the file in bytes."""
    page_size: int
    """Page size (ideal size and thus alignment for efficient access)."""
    access_time: datetime.datetime | None = None
    """Optional information about the latest data access."""
    mod_time: datetime.datetime | None = None
    """Optional information about the latest data modification."""

    class Key(enum.IntEnum):
        """Key in the stat IMap."""

        TYPE = 0
        SIZE = 1
        PAGE_SIZE = 2
        ACCESS_TIME = 3
        MOD_TIME = 4

    def to_shv(self) -> SHVType:
        """Convert to SHV RPC representation."""
        res: dict[int, SHVType] = {
            self.Key.TYPE: 0,
            self.Key.SIZE: self.size,
            self.Key.PAGE_SIZE: self.page_size,
        }
        if self.access_time is not None:
            res[self.Key.ACCESS_TIME] = self.access_time
        if self.mod_time is not None:
            res[self.Key.MOD_TIME] = self.mod_time
        return res

    @classmethod
    def from_shv(cls, value: SHVType) -> RpcFileStat:
        """Create from SHV RPC representation."""
        if not is_shvimap(value):
            raise ValueError("Expected Map.")
        if value.get(cls.Key.TYPE, 0) != 0:
            raise ValueError("Unsupported type")
        return cls(
            size=shvgett(value, cls.Key.SIZE, int, 0),
            page_size=shvgett(value, cls.Key.PAGE_SIZE, int, 128),
            access_time=shvgett(value, cls.Key.ACCESS_TIME, datetime.datetime, None),
            mod_time=shvgett(value, cls.Key.MOD_TIME, datetime.datetime, None),
        )

    @classmethod
    def for_path(cls, path: pathlib.Path | str) -> RpcFileStat:
        """Create stat information for the existing file.

        :param path: Path to the file for which stat should be provided.
        :return: The RPC stat object.
        :raises FileNotFoundError: If there is no such file or if path exists
          but doesn't lead to the file.
        """
        if isinstance(path, str):
            path = pathlib.Path(path)
        if not path.is_file():
            raise FileNotFoundError("Not a regular file")
        stat = path.stat()
        return cls(
            stat.st_size,
            stat.st_blksize,
            datetime.datetime.fromtimestamp(stat.st_atime),
            datetime.datetime.fromtimestamp(stat.st_mtime),
        )


class RpcFile:
    """RPC file accessed over :class:`SimpleBase`.

    :param client:
    :param path:
    :param buffer_read:
    :param buffer_write:
    """

    def __init__(
        self,
        client: SimpleBase,
        path: str,
        buffered: bool = True,
        append: bool = False,
    ) -> None:
        self.client: SimpleBase = client
        """The client used to access the RPC file."""
        self.offset: int = 0
        """Access offset of the file.

        This gets modified by reading and writing from the file. You can also
        set it to perform seek.
        """
        self._path = path
        self._append = False
        self._read_page: int = 0
        self._read_buffer: bytearray | None = bytearray() if buffered else None
        self._write_offset: int = 0
        self._write_buffer: bytearray | None = bytearray() if buffered else None
        self.__page_size: int | None = None

    @property
    def path(self) -> str:
        """SHV path to the file this object is used to access."""
        return self._path

    async def __aenter__(self) -> RpcFile:
        self.offset = 0
        return self

    async def __aexit__(
        self,
        exc_type: type[Exception],
        exc_value: Exception,
        traceback: types.TracebackType,
    ) -> None:
        await self.flush()
        self._read_buffer = bytearray()

    async def __aiter__(self) -> RpcFile:
        return self

    async def __anext__(self) -> bytes:
        res = await self.readline()
        if not res:
            raise StopAsyncIteration
        return res

    async def readable(self) -> bool:
        """Check if file is readable."""
        return await self.client.dir_exists(self._path, "read")

    async def writable(self) -> bool:
        """Check if file is writable with selected write method."""
        return await self.client.dir_exists(
            self._path, "append" if self._append else "write"
        )

    async def resizable(self) -> bool:
        """Check if file is resizable."""
        return await self.client.dir_exists(self._path, "truncate")

    async def stat(self) -> RpcFileStat:
        """Get the file stat info."""
        return RpcFileStat.from_shv(await self.client.call(self._path, "stat"))

    async def _page_size(self) -> int:
        """Get the ideal page size."""
        if self.__page_size is None:
            self.__page_size = (await self.stat()).page_size
        return self.__page_size

    async def read(self, size: int = -1) -> bytes:
        """Read at most given number of bytes.

        :param size: Maximum number of bytes to read. The value 0 or less is the
          no size limit.
        """
        page_size = await self._page_size()
        res = bytearray()
        if self._read_buffer is None:
            while True:
                cnt = size if 0 < size < page_size else page_size
                data = await self.client.call(self._path, "read", [self.offset, cnt])
                if not isinstance(data, bytes) or not data:
                    break
                res += data
                self.offset += len(data)
                if size > 0:
                    size -= len(data)
                    if size == 0:
                        break
        else:
            pass
        return bytes(res)

    async def readline(self, size: int = -1) -> bytes:
        """Read and return one line from the file from the current offset."""
        if self._read_buffer is None:
            raise NotImplementedError(
                "Reading line by line is only supported with buffering"
            )
        res = bytearray()
        while size != 0:
            b = self.read(1)
            if not b:
                break

        return bytes(res)

    async def crc32(self, offset: int | None = 0, size: int | None = None) -> int:
        """Calculate CRC32 checksum of the data.

        :param offset: offset from the file start or current file offset if
          ``None`` is passed.
        :param size: number of bytes since offset used to calculate checksum or
          all of them up to the end of the file in case ``None`` is passed.
        :return: Calculated CRC32 value.
        """
        if offset == 0 and size is None:
            param = None
        else:
            param = [self.offset if offset is None else offset, size]
        res = await self.client.call(self._path, "crc", param)
        return res if isinstance(res, int) else 0

    async def sha1(self, offset: int | None = 0, size: int | None = None) -> bytes:
        """Calculate SHA1 checksum of the data.

        :param offset: offset from the file start or current file offset if
          ``None`` is passed.
        :param size: number of bytes since offset used to calculate checksum or
          all of them up to the end of the file in case ``None`` is passed.
        :return: Calculated SHA1 value.
        """
        if offset == 0 and size is None:
            param = None
        else:
            param = [self.offset if offset is None else offset, size]
        res = await self.client.call(self._path, "sha1", param)
        return res if isinstance(res, bytes) else bytes(20)

    async def _page_write(self, offset: int, data: bytes | bytearray) -> None:
        page_size = await self._page_size()
        while len(data) > page_size:
            param = [self.offset, data[:page_size]]
            await self.client.call(self._path, "write", param)
            data = data[page_size:]

    async def write(self, data: bytes | bytearray) -> None:
        """Write data to the file on the current offset."""
        if self._write_buffer is None:
            if self._append:
                await self.client.call(self._path, "append", data)
            else:
                await self._page_write(self.offset, data)
            return

        if self._append:
            self._write_buffer += data
            return

        page_size = await self._page_size()
        if self._write_offset + len(self._write_buffer) != self.offset:
            await self._page_write(self._write_offset, self._write_buffer)
            self._write_buffer = bytearray()
        if not self._write_buffer:
            self._write_offset = self.offset
        self._write_buffer += data
        if len(self._write_buffer) > page_size:
            # Write what we have so far
            pass

    async def flush(self) -> None:
        """Flush data buffered for write by previous :meth:`write` calls."""
        if self._write_buffer is None:
            return
        if self._append:
            await self.client.call(self._path, "append", self._write_buffer)
        else:
            await self._page_write(self._write_offset, self._write_buffer)
        self._write_buffer = bytearray()

    async def truncate(self, size: int | None = None) -> None:
        """Truncate file size.

        :param size: Truncate to this specific size or to the current offset in
        case of ``None``.
        """
        await self.client.call(
            self._path, "truncate", size if size is not None else self.offset
        )


class RpcTextFile:
    """RPC text file accessed over :class:`SimpleBase`.

    This is based on :class:`RpcFile` with addition that it interprets received
    data as text instead of bytes.
    """

    def __init__(self, file: RpcFile) -> None:
        self.file = file
        raise NotImplementedError

    # TODO


@dataclasses.dataclass
class FileProvider:
    """Implementation helper that provides files over SHV RPC."""

    access_read: RpcMethodAccess = RpcMethodAccess.READ
    """Access level for ``read`` method."""
    access_write: RpcMethodAccess | None = RpcMethodAccess.WRITE
    """Access level for ``write`` method."""
    access_truncate: RpcMethodAccess | None = RpcMethodAccess.WRITE
    """Access level for ``truncate`` method."""
    access_append: RpcMethodAccess | None = RpcMethodAccess.WRITE
    """Access level for ``append`` method."""

    def dir(self) -> collections.abc.Iterator[RpcMethodDesc]:
        """Provide method descriptions for this file access."""
        yield RpcMethodDesc.getter("stat", "Null", "ofstat", self.access_read)
        yield RpcMethodDesc.getter("size", "Null", "Int", self.access_read)
        yield RpcMethodDesc(
            "crc", param="ifcrc", result="UInt", access=self.access_read
        )
        yield RpcMethodDesc(
            "sha1", param="ifsha1", result="Bytes", access=self.access_read
        )
        yield RpcMethodDesc(
            "read",
            RpcMethodFlags.LARGE_RESULT_HINT,
            "ifread",
            "Bytes",
            self.access_read,
        )
        if self.access_write is not None:
            yield RpcMethodDesc(
                "write", param="ifwrite", result="Null", access=self.access_write
            )
        if self.access_truncate is not None:
            yield RpcMethodDesc(
                "truncate", param="Int", result="Null", access=self.access_truncate
            )
        if self.access_append is not None:
            yield RpcMethodDesc(
                "append", param="Bytes", result="Null", access=self.access_append
            )

    def method(
        self,
        path: pathlib.Path,
        name: str,
        param: SHVType,
        access_level: RpcMethodAccess,
    ) -> SHVType:
        """File access methods implementation.

        :param path: Path to the file that should be accessed. This is not SHV
          path but rather a real local file path.
        :param name: Name of the method that is called.
        :param param: Parameter provided to the method call.
        :param access_level: The access level for the method call.
        :return: The value that should be provided as result of the method call.
        :raises FileNotFoundError: If file pointed to by ``path`` doesn't
          exists.
        :raises RpcInvalidParamsError: If parameter is invalid.
        :raises NotImplementedError: If requested method is not implemented or
          too low access level was provided.
        """
        match name:
            case "stat" if access_level >= self.access_read:
                return RpcFileStat.for_path(path).to_shv()
            case "size" if access_level >= self.access_read:
                return path.stat().st_size
            case "crc" if access_level >= self.access_read:
                offset = shvargt(param, 0, int, 0)
                size = shvargt(param, 1, int, None)
                crc = binascii.crc32(b"")
                with path.open("rb") as file:
                    file.seek(offset)
                    while size is None or size > 0:
                        data = file.read(
                            io.DEFAULT_BUFFER_SIZE
                            if size is None
                            else min(size, io.DEFAULT_BUFFER_SIZE)
                        )
                        if not data:
                            break
                        crc = binascii.crc32(data, crc)
                        if size is not None:
                            size -= len(data)
                return crc
            case "sha1" if access_level >= self.access_read:
                offset = shvargt(param, 0, int, 0)
                size = shvargt(param, 1, int, None)
                hash = hashlib.sha1()  # noqa PLR6301
                with path.open("rb") as file:
                    file.seek(offset)
                    while size is None or size > 0:
                        data = file.read(
                            io.DEFAULT_BUFFER_SIZE
                            if size is None
                            else min(size, io.DEFAULT_BUFFER_SIZE)
                        )
                        if not data:
                            break
                        hash.update(data)
                        if size is not None:
                            size -= len(data)
                return hash.digest()
            case "read" if access_level >= self.access_read:
                offset = shvargt(param, 0, int)
                size = shvargt(param, 1, int)
                with path.open("rb") as file:
                    file.seek(offset)
                    return file.read(size)
            case "write" if self.access_write is not None and access_level >= self.access_write:
                offset = shvargt(param, 0, int)
                data = shvargt(param, 1, bytes)
                if (
                    self.access_truncate is None
                    and (offset + len(data)) > path.stat().st_size
                ):
                    raise RpcInvalidParamsError(
                        "Write beyond the file boundary is not possible"
                    )
                with path.open("wb") as file:
                    file.seek(offset)
                    file.write(data)
                return None
            case "truncate" if self.access_truncate is not None and access_level >= self.access_truncate:
                size = shvt(param, int)
                with path.open("wb") as file:
                    file.truncate(size)
                return None
            case "append" if self.access_append is not None and access_level >= self.access_append:
                data = shvt(param, bytes)
                with path.open("ab") as file:
                    file.write(data)
                return None
        raise NotImplementedError


FileProviderRO = FileProvider(
    access_read=RpcMethodAccess.READ,
    access_write=None,
    access_truncate=None,
    access_append=None,
)
"""RPC File provider for read-only file access."""
FileProviderRW = FileProvider(
    access_read=RpcMethodAccess.READ,
    access_write=RpcMethodAccess.WRITE,
    access_truncate=RpcMethodAccess.WRITE,
    access_append=RpcMethodAccess.WRITE,
)
"""RPC File provider for read-write access to the files."""
FileProviderFixedSize = FileProvider(
    access_read=RpcMethodAccess.READ,
    access_write=RpcMethodAccess.WRITE,
    access_truncate=None,
    access_append=None,
)
"""RPC File provider for read-write access to the files of fixed size."""
FileProviderAppend = FileProvider(
    access_read=RpcMethodAccess.READ,
    access_write=None,
    access_truncate=None,
    access_append=RpcMethodAccess.WRITE,
)
"""RPC File provider that aprovides write access but only through appends."""
