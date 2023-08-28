"""RPC connection, that includes client and specific server connection."""
from __future__ import annotations

import abc
import asyncio
import binascii
import collections.abc
import functools
import io
import logging
import time
import typing

import serial
import serial_asyncio

from .chainpack import ChainPack, ChainPackReader, ChainPackWriter
from .cpon import Cpon, CponReader
from .rpcmessage import RpcMessage
from .rpcurl import RpcProtocol, RpcUrl

logger = logging.getLogger(__name__)


class RpcClient(abc.ABC):
    """RPC connection to some SHV peer."""

    def __init__(self):
        self.last_send = time.monotonic()
        """Monotonic time when last message was sent on this connection.

        The initial value is time of the RpcClient creation.
        """
        self.last_receive = time.monotonic()
        """Monotonic time when last message was received on this connection.

        The initial value is time of the RpcClient creation.
        """

    async def send(self, msg: RpcMessage) -> None:
        """Send the given SHV RPC Message.

        :param msg: Message to be sent
        """
        self.last_send = time.monotonic()
        logger.debug("<== SND: %s", msg.to_string())

    async def receive(self, raise_error: bool = True) -> typing.Optional[RpcMessage]:
        """Read next received RPC message or wait for next to be received.

        :param raise_error: If RpcError should be raised or not.
        :return: Next RPC message is returned or `None` in case of EOF.
        :raise RpcError: When mesasge is error and ``raise_error`` is `True`.
        """
        data = await self._receive()
        self.last_receive = time.monotonic()
        if data is None:
            return None
        proto = data[0]
        rd = ChainPackReader if proto == 1 else CponReader if proto == 2 else None
        if rd is None:
            # TODO we need to implement error that disconnects this client
            raise NotImplementedError
        msg = RpcMessage(rd(io.BytesIO(data[1:])).read())
        logger.debug("==> REC: %s", msg.to_string())
        if raise_error and msg.is_error():
            error = msg.rpc_error()
            assert error is not None
            raise error
        return msg

    @abc.abstractmethod
    async def _receive(self) -> bytes | None:
        """Implementation of :meth:`receive` (an actual message receive)."""

    async def reset(self) -> None:
        """Reset the connection.

        Attempt to reset the connection.

        This might just close the link without opening it again! You should call
        :meth:`connected` after this one to check if you have a connection.

        It is common that we use connection tracking native to the link layer
        and reset is performed by really closing the connection and establishing a new
        one but that might not be available for servers.
        """
        if not self.connected():
            raise RuntimeError("Reset can be called only on connected client.")
        logger.debug("==> RESET")
        await self._reset()

    @abc.abstractmethod
    async def _reset(self) -> None:
        """Implementation of :meth:`reset`."""

    @abc.abstractmethod
    def connected(self) -> bool:
        """Check if client is still connected.

        This is only local check. There is no communication done and thus depending on
        the transport layer this can be pretty much a lie. The only reliable tests is
        sending request and receiving respond to it.

        :return: ``True`` if client might still connected and ``False`` if we know that
            it is not.
        """

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close the connection."""


class RpcClientStream(RpcClient):
    """RPC connection to some SHV peer over stream transport layer.

    You most likely want to use :func:`connect` class methods instead of
    initializing this class directly.

    :param reader: Reader for the connection to the SHV RPC server.
    :param writer: Writer for the connection to the SHV RPC server.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        reconnect: None
        | typing.Callable[
            [RpcClientStream],
            collections.abc.Awaitable[
                typing.Tuple[asyncio.StreamReader, asyncio.StreamWriter]
            ],
        ] = None,
    ):
        super().__init__()
        self.reader = reader
        self.writer = writer
        self.reconnect = reconnect
        self._read_data = bytearray(0)

    @classmethod
    async def connect(
        cls,
        location: str | None = None,
        port: int = 3755,
    ) -> RpcClient:
        """Connect to the SHV RPC server over TCP/IP.

        :param location: IP/Hostname (TCP)
        :param port: Port (TCP) to connect to
        """
        logger.debug("Connecting to: (TCP) %s:%d", location, port)
        reconnect = functools.partial(
            asyncio.open_connection,
            location if location is not None else "localhost",
            port,
        )
        reader, writer = await reconnect()
        client = cls(reader, writer, lambda _: reconnect())
        logger.debug("TCP CONNECTED")
        return client

    @classmethod
    async def unix_connect(
        cls,
        location: str | None = None,
    ) -> RpcClient:
        """Connect to the SHV RPC server over Unix (local) socket.

        :param location: socket path
        """
        logger.debug("Connecting to: (UNIX) %s", location)
        reconnect = functools.partial(
            asyncio.open_unix_connection,
            path=location if location is not None else "shv.sock",
        )
        reader, writer = await reconnect()
        client = cls(reader, writer, lambda _: reconnect())
        logger.debug("UNIX CONNECTED")
        return client

    async def send(self, msg: RpcMessage) -> None:
        data = msg.to_chainpack()
        writer = ChainPackWriter(self.writer)
        writer.write_uint_data(len(data) + 1)
        self.writer.write(bytes((ChainPack.ProtocolType,)))
        self.writer.write(data)
        await super().send(msg)
        await self.writer.drain()

    async def _receive(self) -> bytes | None:
        while not self.reader.at_eof():
            size = 0
            try:
                reader = ChainPackReader(io.BytesIO(self._read_data))
                size = reader.read_uint_data()
                off = reader.bytes_cnt
            except EOFError:
                pass
            if size > 0 and (off + size) <= len(self._read_data):
                msg = self._read_data[off : off + size]
                self._read_data = self._read_data[off + size :]
                return msg
            self._read_data += await self.reader.read(1024)
        return None

    async def _reset(self) -> None:
        if self.reconnect is not None:
            self.writer.close()
            self.reader, self.writer = await self.reconnect(self)
        else:
            await self.disconnect()

    def connected(self) -> bool:
        return not self.writer.is_closing()

    async def disconnect(self) -> None:
        self.writer.close()
        await self.writer.wait_closed()


class RpcClientDatagram(RpcClient):
    """RPC connection to some SHV peer over datagram transport layer.

    You most likely want to use :func:`connect` class methods instead of
    initializing this class directly.
    """

    class _Protocol(asyncio.DatagramProtocol):
        """Implementation of Asyncio datagram protocol to communicate over UDP."""

        def __init__(self) -> None:
            self.queue: asyncio.Queue[bytes] = asyncio.Queue()

        def datagram_received(self, data: bytes, _) -> None:
            # Note: empty messages are ignored because they are commonly used to setup
            # the new connection on both sides.
            if data:
                self.queue.put_nowait(data)

        def connection_lost(self, exc):
            self.queue.put_nowait(None)

    def __init__(
        self,
        transport: asyncio.DatagramTransport,
        protocol: _Protocol,
    ) -> None:
        super().__init__()
        self._transport = transport
        self._protocol = protocol

    @classmethod
    async def connect(
        cls,
        location: str | None = None,
        port: int = 3755,
    ) -> RpcClient:
        """Connect to the SHV RPC server over UDP.

        :param location: IP/Hostname
        :param port: Port to connect to
        """
        t, p = await asyncio.get_running_loop().create_datagram_endpoint(
            cls._Protocol, remote_addr=(location or "localhost", port)
        )
        logger.debug("Connected to: (UDP) %s:%d", location, port)
        return cls(t, p)

    async def send(self, msg: RpcMessage) -> None:
        await super().send(msg)
        self._transport.sendto(bytes((ChainPack.ProtocolType,)) + msg.to_chainpack())

    async def _receive(self) -> bytes | None:
        msg = await self._protocol.queue.get()
        self._protocol.queue.task_done()
        return msg

    async def _reset(self) -> None:
        # We actually do not need to perform reset because there is nothing to reset. We
        # use this rather to setup UDP client on the server.
        self._transport._sock.send(bytes())  # type: ignore

    def connected(self) -> bool:
        return not self._transport.is_closing()

    async def disconnect(self) -> None:
        self._transport.close()


class RpcClientSerial(RpcClient):
    """RPC connection to some SHV peer over serial transport layer.

    You most likely want to use :func:`open` class methods instead of
    initializing this class directly.

    :param reader: Reader for the connection to the SHV RPC server.
    :param writer: Writer for the connection to the SHV RPC server.
    """

    STX = 0xA2
    ETX = 0xA3
    ESTX = 0xA4
    EETX = 0xA5
    ESC = 0xAA

    def __init__(
        self,
        serial_instance: serial.Serial,
        loop=None,
    ):
        super().__init__()
        self.serial = serial_instance
        self._loop = loop if loop is not None else asyncio.get_running_loop()

        self.reader = asyncio.StreamReader(loop=loop)
        self.protocol = asyncio.StreamReaderProtocol(self.reader, loop=self._loop)
        self.transport = serial_asyncio.SerialTransport(
            self._loop, self.protocol, self.serial
        )
        self.writer = asyncio.StreamWriter(
            self.transport, self.protocol, self.reader, self._loop
        )
        self._read_data = bytearray(0)

    @classmethod
    async def open(
        cls,
        port: str | None = None,
        baudrate: int = 115200,
    ) -> RpcClient:
        """Connect to the SHV RPC server over TCP or LOCAL_SOCKET.

        :param port: Path to the port (Unix) or port name (Windows).
        :param baudrate: Baudrate to be used on the port.
        """
        logger.debug("Connecting to: (SERIALPORT) %s[%d]", port, baudrate)
        s = serial.Serial(
            port=port, baudrate=baudrate, rtscts=True, dsrdtr=True, exclusive=True
        )
        client = cls(s)
        logger.debug("SERIALPORT CONNECTED")
        return client

    async def send(self, msg: RpcMessage) -> None:
        bts = [ChainPack.ProtocolType]
        for byte in msg.to_chainpack():
            if byte == self.STX:
                bts.extend((self.ESC, self.ESTX))
            elif byte == self.ETX:
                bts.extend((self.ESC, self.EETX))
            elif byte == self.ESC:
                bts.extend((self.ESC, self.ESC))
            else:
                bts.append(byte)
        data = bytes(bts)
        self.writer.write(bytes((self.STX,)))
        self.writer.write(data)
        self.writer.write(bytes((self.ETX,)))
        # TODO validate the crc32 alhorithm
        self.writer.write(binascii.crc32(data).to_bytes(4, "big"))
        await super().send(msg)
        await self.writer.drain()

    async def _receive(self) -> bytes | None:
        while True:
            if self.STX in self._read_data:
                # Drop anything before STX
                self._read_data = self._read_data[self._read_data.index(self.STX) :]
            while self.ETX in self._read_data:
                etxi = self._read_data.index(self.ETX)
                stxi = self._read_data.rindex(self.STX, 0, etxi)
                # Process message if we have it fully (ETX+4(CRC32))
                if etxi + 4 > len(self._read_data):
                    break
                data = self._read_data[stxi + 1 : etxi]
                crc32 = int.from_bytes(self._read_data[etxi + 1 : etxi + 6], "big")
                self._read_data = self._read_data[etxi + 5 :]
                if crc32 == binascii.crc32(data):
                    bts = []
                    i = 0
                    while i < (etxi - stxi - 1):
                        byte = data[i]
                        if byte == self.ESC:
                            i += 1
                            byte = data[i]
                            if byte == self.ESTX:
                                byte = self.STX
                            elif byte == self.EETX:
                                byte = self.ETX
                        bts.append(byte)
                        i += 1
                    if bts:  # ignore empty messages as they only reset stream
                        return bytes(bts)
            try:
                self._read_data += await self.reader.read(1024)
            except serial.serialutil.SerialException:
                return None

    async def _reset(self) -> None:
        # TODO validate if we should not reopen the serial
        self.writer.write(bytes((self.STX, self.ETX)))
        self.writer.write(binascii.crc32(bytes()).to_bytes(4, "big"))
        await self.writer.drain()

    def connected(self) -> bool:
        return not self.writer.is_closing()

    async def disconnect(self) -> None:
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except serial.serialutil.SerialException:
            pass


async def connect_rpc_client(url: RpcUrl) -> RpcClient:
    """Connect to the server on given URL.

    :param url: RPC URL specifying the server location.
    """
    if url.protocol is RpcProtocol.TCP:
        return await RpcClientStream.connect(url.location, url.port)
    if url.protocol is RpcProtocol.LOCAL_SOCKET:
        return await RpcClientStream.unix_connect(url.location)
    if url.protocol is RpcProtocol.UDP:
        return await RpcClientDatagram.connect(url.location, url.port)
    if url.protocol is RpcProtocol.SERIAL:
        return await RpcClientSerial.open(url.location, url.baudrate)
    raise NotImplementedError(f"Unimplemented protocol: {url.protocol}")
