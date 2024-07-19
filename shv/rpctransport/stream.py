"""Common base for stream based clients."""

from __future__ import annotations

import abc
import asyncio
import binascii
import collections.abc
import contextlib
import logging
import typing
import weakref

from ..chainpack import ChainPack
from .abc import RpcClient, RpcServer

logger = logging.getLogger(__name__)


class RpcTransportProtocol(abc.ABC):
    """Base for the implementations of RPC transport protocols."""

    @classmethod
    @abc.abstractmethod
    async def send(
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
    ) -> None:
        """Send message.

        :param msg: Bytes of a complete message to be sent.
        """

    @classmethod
    @abc.abstractmethod
    async def receive(
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
    ) -> bytes:
        """Receive message.

        :return: Bytes of complete message.
        :raise EOFError: when EOF is encountered.
        """

    @classmethod
    async def asyncio_send(cls, writer: asyncio.StreamWriter, msg: bytes) -> None:
        """Variation on :meth:`send` that uses :class:`asyncio.StreamWriter`."""

        async def write(d: bytes) -> None:
            writer.write(d)
            await writer.drain()

        await cls.send(write, msg)

    @classmethod
    async def asyncio_receive(cls, reader: asyncio.StreamReader) -> bytes:
        """Variation on :meth:`receive` that uses :class:`asyncio.StreamReader`."""

        async def read(n: int) -> bytes:
            try:
                return await reader.readexactly(n)
            except (asyncio.IncompleteReadError, ConnectionError) as exc:
                raise EOFError from exc

        return await cls.receive(read)


class RpcProtocolStream(RpcTransportProtocol):
    """SHV RPC Stream protocol."""

    @classmethod
    async def send(  # noqa: D102
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
    ) -> None:
        await write(ChainPack.pack_uint_data(len(msg)))
        await write(msg)

    @classmethod
    async def receive(  # noqa: D102
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
    ) -> bytes:
        sdata = bytearray()
        while True:
            sdata += await read(1)
            try:
                size = ChainPack.unpack_uint_data(sdata)
            except ValueError:
                pass
            else:
                return await read(size)


class _RpcProtocolSerial(RpcTransportProtocol):
    """SHV RPC Serial protocol."""

    STX = 0xA2
    ETX = 0xA3
    ATX = 0xA4
    ESC = 0xAA
    ESCMAP: typing.Final = {0x02: STX, 0x03: ETX, 0x04: ATX, 0x0A: ESC}
    ESCRMAP: typing.Final = {v: k for k, v in ESCMAP.items()}

    @classmethod
    async def _send(
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
        use_crc: bool,
    ) -> None:
        await write(bytes((cls.STX,)))
        escmsg = cls.escape(msg)
        await write(escmsg)
        await write(bytes((cls.ETX,)))
        if use_crc:
            await write(cls.escape(binascii.crc32(escmsg).to_bytes(4, "big")))

    @classmethod
    def escape(cls, data: bytes) -> bytes:
        """Escape bytes as defined for serial protocol.

        :param data: Data to be escaped (node that you can pass
          :class:`bytearray` to modify in place).
        :return: The modified data.
        """
        # Warning: ESC must be first in the list so we first replace all occurances of
        # ESC before we insert more of them.
        for b in (cls.ESC, cls.STX, cls.ETX, cls.ATX):
            data = data.replace(bytes((b,)), bytes((cls.ESC, cls.ESCRMAP[b])))
        return data

    @classmethod
    async def _receive(
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
        use_crc: bool,
    ) -> bytes:
        while True:
            while (await read(1))[0] != cls.STX:
                pass
            data = bytearray()
            while (b := (await read(1))[0]) not in {cls.ETX, cls.ATX}:
                data += bytes((b,))
            if b == cls.ATX:
                continue
            if use_crc:
                crc32_br = bytearray()
                while len(crc32_br) < (siz := 4 + crc32_br.count(bytes((cls.ESC,)))):
                    crc32_br += await read(siz - len(crc32_br))
                crc32_b = cls.deescape(crc32_br)
                if int.from_bytes(crc32_b, "big") != binascii.crc32(data):
                    continue
            return cls.deescape(data)

    @classmethod
    def deescape(cls, data: bytes) -> bytes:
        """Reverse escape operation on bytes as defined for serial protocol.

        :param data: Escaped data (node that you can pass :class:`bytearray` to
          modify in place).
        :return: The modified data.
        """
        for b in (cls.STX, cls.ETX, cls.ATX, cls.ESC):
            data = data.replace(bytes((cls.ESC, cls.ESCRMAP[b])), bytes((b,)))
        return data


class RpcProtocolSerial(_RpcProtocolSerial):
    """SHV RPC Serial protocol."""

    @classmethod
    async def send(  # noqa: D102
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
    ) -> None:
        await cls._send(write, msg, False)

    @classmethod
    async def receive(  # noqa: D102
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
    ) -> bytes:
        return await cls._receive(read, False)


class RpcProtocolSerialCRC(_RpcProtocolSerial):
    """SHV RPC Serial protocol with CRC32 message validation."""

    @classmethod
    async def send(  # noqa: D102
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
    ) -> None:
        await cls._send(write, msg, True)

    @classmethod
    async def receive(  # noqa: D102
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
    ) -> bytes:
        return await cls._receive(read, True)


class RpcClientStream(RpcClient):
    """RPC connection to some SHV peer over data stream."""

    def __init__(
        self,
        protocol: type[RpcTransportProtocol] = RpcProtocolStream,
    ) -> None:
        super().__init__()
        self._reader: None | asyncio.StreamReader = None
        self._writer: None | asyncio.StreamWriter = None
        self.protocol = protocol
        """Stream communication protocol."""

    async def _send(self, msg: bytes) -> None:
        if self._writer is None:
            raise EOFError("Not connected")
        try:
            await self.protocol.asyncio_send(self._writer, msg)
        except ConnectionError as exc:
            raise EOFError from exc

    async def _receive(self) -> bytes:
        if self._reader is None:
            raise EOFError("Not connected")
        try:
            return await self.protocol.asyncio_receive(self._reader)
        except EOFError:
            if self._writer is not None:
                self._writer.close()
            raise

    async def reset(self) -> None:
        """Reset or establish the connection.

        This method not only resets the existing connection but primarilly
        estableshes the new one.
        """
        if not self.connected:
            self._reader, self._writer = await self._open_connection()
            logger.debug("%s: Connected", self)
        else:
            await super().reset()

    @abc.abstractmethod
    async def _open_connection(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        pass

    @property
    def connected(self) -> bool:
        """Check if client is still connected."""
        return self._writer is not None and not self._writer.is_closing()

    def _disconnect(self) -> None:
        if self._writer is not None:
            self._writer.close()

    async def wait_disconnect(self) -> None:
        """Wait for the client's disconnection."""
        if self._writer is not None:
            with contextlib.suppress(ConnectionError):
                await self._writer.wait_closed()


class RpcServerStream(RpcServer):
    """RPC server listenting for SHV connections for streams."""

    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        protocol: type[RpcTransportProtocol] = RpcProtocolStream,
    ) -> None:
        self.client_connected_cb = client_connected_cb
        """Callbact that is called when new client is connected."""
        self.protocol = protocol
        """Stream communication protocol."""
        self._server: asyncio.Server | None = None
        self._clients: weakref.WeakSet[RpcServerStream.Client] = weakref.WeakSet()

    @abc.abstractmethod
    async def _create_server(self) -> asyncio.Server:
        """Create the server instance."""

    def is_serving(self) -> bool:
        """Check if server is accepting new SHV connections."""
        return self._server is not None and self._server.is_serving()

    async def listen(self) -> None:
        """Start accepting new SHV connections."""
        if self._server is None:
            self._server = await self._create_server()
        await self._server.start_serving()

    async def listen_forewer(self) -> None:
        """Listen and block the calling coroutine until cancelation."""
        if self._server is None:
            self._server = await self._create_server()
        await self._server.serve_forever()

    async def _client_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        client = self.Client(reader, writer, self)
        self._clients.add(client)
        res = self.client_connected_cb(client)
        if isinstance(res, collections.abc.Awaitable):
            await res

    def close(self) -> None:  # noqa D102
        if self._server is not None:
            self._server.close()

    async def wait_closed(self) -> None:  # noqa D102
        if self._server is not None:
            await self._server.wait_closed()

    def terminate(self) -> None:  # noqa D102
        self.close()
        for client in self._clients:
            client.disconnect()

    async def wait_terminated(self) -> None:  # noqa D102
        await self.wait_closed()
        res = await asyncio.gather(
            *(c.wait_disconnect() for c in self._clients),
            return_exceptions=True,
        )
        excs = [v for v in res if isinstance(v, BaseException)]
        if excs:
            if len(excs) == 1:
                raise excs[0]
            raise BaseExceptionGroup("", excs)

    class Client(RpcClient):
        """RPC client for Asyncio's stream server connection."""

        def __init__(
            self,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
            server: RpcServerStream,
        ) -> None:
            super().__init__()
            self._reader = reader
            self._writer = writer
            self.protocol = server.protocol
            """Stream communication protocol."""

        async def _send(self, msg: bytes) -> None:
            try:
                await self.protocol.asyncio_send(self._writer, msg)
            except ConnectionError as exc:
                raise EOFError from exc

        async def _receive(self) -> bytes:
            try:
                return await self.protocol.asyncio_receive(self._reader)
            except EOFError:
                self._writer.close()
                raise

        @property
        def connected(self) -> bool:
            """Check if client is still connected."""
            return not self._writer.is_closing()

        def _disconnect(self) -> None:
            self._writer.close()

        async def wait_disconnect(self) -> None:
            """Wait for the client's disconnection."""
            with contextlib.suppress(ConnectionError):
                await self._writer.wait_closed()
