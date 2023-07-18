"""RPC connection, that includes client and specific server connection."""
from __future__ import annotations

import abc
import asyncio
import io
import logging
import time
import typing

from .chainpack import ChainPack, ChainPackReader, ChainPackWriter
from .cpon import Cpon, CponReader
from .rpcmessage import RpcMessage
from .rpcurl import RpcProtocol

logger = logging.getLogger(__name__)


class RpcClient(abc.ABC):
    """RPC connection to some SHV peer."""

    def __init__(self):
        self.last_activity = time.monotonic()
        """Last activity on this connection (read or write of the message)."""

    def _mark_activity(self):
        """Mark that there was an activity received from the peer."""
        self.last_activity = time.monotonic()

    async def send(self, msg: RpcMessage) -> None:
        """Send the given SHV RPC Message.

        :param msg: Message to be sent
        """
        logger.debug("<== SND: %s", msg.to_string())

    async def receive(self, raise_error: bool = True) -> typing.Optional[RpcMessage]:
        """Read next received RPC message or wait for next to be received.

        :param raise_error: If RpcError should be raised or not.
        :return: Next RPC message is returned or `None` in case of EOF.
        :raise RpcError: When mesasge is error and ``raise_error`` is `True`.
        """
        data = await self._receive()
        self._mark_activity()
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
        """Implementation of :meth:`receive` actual message receive."""

    @abc.abstractmethod
    def connected(self) -> bool:
        """Check if client is still connected.

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
    ):
        super().__init__()
        self.reader = reader
        self.writer = writer
        self._read_data = bytearray(0)

    @classmethod
    async def connect(
        cls,
        location: str | None = None,
        port: int = 3755,
        protocol: RpcProtocol = RpcProtocol.TCP,
    ) -> RpcClient:
        """Connect to the SHV RPC server over TCP or LOCAL_SOCKET.

        :param location: IP/Hostname (TCP) or socket path (LOCKAL_SOCKET)
        :param port: Port (TCP) to connect to
        :param protocol: Protocol used to connect to the server
        """
        if protocol not in (RpcProtocol.TCP, RpcProtocol.LOCAL_SOCKET):
            raise RuntimeError(f"Invalid protocol: {protocol}")
        logger.debug("Connecting to: (%s) %s:%d", protocol.name, location, port)
        if protocol == RpcProtocol.TCP:
            reader, writer = await asyncio.open_connection(
                location if location is not None else "localhost", port
            )
        elif protocol == RpcProtocol.LOCAL_SOCKET:
            reader, writer = await asyncio.open_unix_connection(
                location if location is not None else "shv.sock"
            )
        client = cls(reader, writer)
        logger.debug("%s CONNECTED", str(protocol))
        return client

    async def send(self, msg: RpcMessage) -> None:
        data = msg.to_chainpack()
        writer = ChainPackWriter(self.writer)
        writer.write_uint_data(len(data) + 1)
        self.writer.write(ChainPack.ProtocolType.to_bytes(1, "big"))
        self.writer.write(data)
        await super().send(msg)
        await self.writer.drain()

    async def _receive(self) -> bytes | None:
        while not self.reader.at_eof():
            size: int = 0
            if size == 0:
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
            self._mark_activity()
        return None

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
        protocol: RpcProtocol = RpcProtocol.UDP,
    ) -> RpcClient:
        """Connect to the SHV RPC server over UDP.

        :param location: IP/Hostname
        :param port: Port to connect to
        :param protocol: Protocol used to connect to the server (for future extensibility)
        """
        if protocol is not RpcProtocol.UDP:
            raise RuntimeError(f"Invalid protocol: {protocol}")
        t, p = await asyncio.get_running_loop().create_datagram_endpoint(
            cls._Protocol, remote_addr=(location or "localhost", port)
        )
        logger.debug("Connected to: (%s) %s:%d", protocol.name, location, port)
        return cls(t, p)

    async def send(self, msg: RpcMessage) -> None:
        await super().send(msg)
        self._transport.sendto(b"\x01" + msg.to_chainpack())

    async def _receive(self) -> bytes | None:
        msg = await self._protocol.queue.get()
        self._protocol.queue.task_done()
        return msg

    def connected(self) -> bool:
        return not self._transport.is_closing()

    async def disconnect(self) -> None:
        self._transport.close()
