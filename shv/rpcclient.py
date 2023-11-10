"""RPC connection, that includes client and specific server connection."""
from __future__ import annotations

import abc
import asyncio
import logging
import time
import typing

import aioserial

from . import rpcprotocol
from .chainpack import ChainPack
from .rpcmessage import RpcMessage
from .rpcprotocol import (
    RpcProtocolSerial,
    RpcProtocolSerialCRC,
    RpcProtocolStream,
    RpcTransportProtocol,
)
from .rpcurl import RpcProtocol, RpcUrl
from .value import SHVIMap, SHVType

logger = logging.getLogger(__name__)


class RpcClient(abc.ABC):
    """RPC connection to some SHV peer."""

    def __init__(self) -> None:
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
        await self._send(bytearray((ChainPack.ProtocolType,)) + msg.to_chainpack())
        self.last_send = time.monotonic()
        logger.debug("<== SND: %s", msg.to_string())

    @abc.abstractmethod
    async def _send(self, msg: bytes) -> None:
        """Implementation of message sending."""

    async def receive(self, raise_error: bool = True) -> RpcMessage:
        """Read next received RPC message or wait for next to be received.

        :param raise_error: If RpcError should be raised or not.
        :return: Next RPC message is returned or `None` in case of EOF.
        :raise RpcError: When mesasge is error and ``raise_error`` is `True`.
        :raise EOFError: in case EOF is encountered.
        """
        shvdata: SHVType = None
        while True:
            data = await self._receive()
            self.last_receive = time.monotonic()
            if len(data) > 1 and data[0] == ChainPack.ProtocolType:
                try:
                    shvdata = ChainPack.unpack(data[1:])
                except ValueError:
                    pass
                else:
                    if isinstance(shvdata, SHVIMap):
                        break
            logger.debug("==> Invalid message received: %s", data)

        msg = RpcMessage(shvdata)
        logger.debug("==> REC: %s", msg.to_string())
        if raise_error and msg.is_error:
            raise msg.rpc_error
        return msg

    @abc.abstractmethod
    async def _receive(self) -> bytes:
        """Implementation of message receive.

        :return: bytes of received message (complete valid message).
        :raise EOFError: if end of the connection is encountered.
        """

    @property
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
    async def reset(self) -> bool:
        """Reset the connection.

        Attempt to reset the connection.

        This might just close the link without opening it again!

        It is common that we use connection tracking native to the link layer and reset
        is performed by really closing the connection and establishing a new one but
        that might not be available for all implementations and especially not for
        servers.

        :return: ``True`` if client is connected after reset and ``False`` otherwise.
        """

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Close the connection."""

    async def wait_disconnect(self) -> None:
        """Close the connection."""


class _RpcClientStream(RpcClient):
    """RPC connection to some SHV peer over data stream."""

    def __init__(
        self,
        protocol_factory: typing.Type[RpcTransportProtocol] = RpcProtocolStream,
    ) -> None:
        super().__init__()
        self._reader: None | asyncio.StreamReader = None
        self._writer: None | asyncio.StreamWriter = None
        self._protocol: RpcTransportProtocol | None = None
        self.protocol_factory = protocol_factory

    async def _send(self, msg: bytes) -> None:
        if self._protocol is not None:
            await self._protocol.send(msg)
        # Drop message if not connected

    async def _receive(self) -> bytes:
        if self._protocol is None:
            raise EOFError("Not connected")
        return await self._protocol.receive()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    def disconnect(self) -> None:
        if self._writer is not None:
            self._writer.close()

    async def wait_disconnect(self) -> None:
        if self._writer is not None:
            await self._writer.wait_closed()


class RpcClientTCP(_RpcClientStream):
    """RPC connection to some SHV peer over TCP/IP."""

    def __init__(
        self,
        location: str,
        port: int,
        protocol_factory: typing.Type[RpcTransportProtocol],
    ) -> None:
        super().__init__(protocol_factory)
        self.location = location
        self.port = port

    async def reset(self) -> bool:
        self.disconnect()
        self._reader, self._writer = await asyncio.open_connection(
            self.location, self.port
        )
        self._protocol = rpcprotocol.protocol_for_asyncio_stream(
            self.protocol_factory, self._reader, self._writer
        )
        logger.debug("Connected to: (TCP) %s:%d", self.location, self.port)
        return True

    def disconnect(self) -> None:
        if self.connected:
            logger.debug("Disconnecting from: (TCP) %s:%d", self.location, self.port)
        super().disconnect()

    @classmethod
    async def connect(
        cls,
        location: str = "localhost",
        port: int = 3755,
        protocol_factory: typing.Type[RpcTransportProtocol] = RpcProtocolStream,
    ) -> RpcClientTCP:
        res = cls(location, port, protocol_factory)
        await res.reset()
        return res


class RpcClientUnix(_RpcClientStream):
    """RPC connection to some SHV peer over Unix domain named socket."""

    def __init__(
        self,
        location: str,
        protocol_factory: typing.Type[RpcTransportProtocol],
    ) -> None:
        super().__init__(protocol_factory)
        self.location = location

    async def reset(self) -> bool:
        if self.connected:
            self.disconnect()
        self._reader, self._writer = await asyncio.open_unix_connection(self.location)
        self._protocol = rpcprotocol.protocol_for_asyncio_stream(
            self.protocol_factory, self._reader, self._writer
        )
        logger.debug("Connected to: (Unix) %s", self.location)
        return True

    def disconnect(self) -> None:
        if self.connected:
            logger.debug("Disconnecting from: (Unix) %s", self.location)
        super().disconnect()

    @classmethod
    async def connect(
        cls,
        location: str = "shv.sock",
        protocol_factory: typing.Type[RpcTransportProtocol] = RpcProtocolStream,
    ) -> RpcClientUnix:
        res = cls(location, protocol_factory)
        await res.reset()
        return res


class RpcClientTTY(RpcClient):
    """RPC connection to some SHV peer over Unix domain named socket."""

    def __init__(
        self,
        port: str,
        baudrate: int,
        protocol_factory: typing.Type[RpcTransportProtocol],
    ) -> None:
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.protocol_factory = protocol_factory
        self.serial: None | aioserial.AioSerial = None
        self._protocol: None | RpcTransportProtocol = None

    async def _send(self, msg: bytes) -> None:
        if self._protocol is not None:
            await self._protocol.send(msg)

    async def _receive(self) -> bytes:
        if self._protocol is None:
            raise EOFError
        return await self._protocol.receive()

    @property
    def connected(self) -> bool:
        return self.serial is not None and self.serial.is_open

    async def reset(self) -> bool:
        self.disconnect()
        self.serial = aioserial.AioSerial(
            port=self.port,
            baudrate=self.baudrate,
            rtscts=True,
            dsrdtr=True,
            exclusive=True,
        )
        self._protocol = self.protocol_factory(
            self._read_exactly, self.serial.write_async
        )
        logger.debug("Connected to: (TTY) %s", self.port)
        return True

    async def _read_exactly(self, n: int) -> bytes:
        assert self.serial is not None
        res = bytearray()
        while len(res) < n:
            try:
                res += await self.serial.read_async(n - len(res))
            except aioserial.SerialException as exc:
                raise EOFError from exc
        return res

    def disconnect(self) -> None:
        if self.serial is not None and self.serial.is_open:
            self.serial.close()
            logger.debug("Disconnecting from: (TTY) %s", self.port)

    @classmethod
    async def open(
        cls,
        port: str,
        baudrate: int = 115200,
        protocol_factory: typing.Type[RpcTransportProtocol] = RpcProtocolSerialCRC,
    ) -> RpcClientTTY:
        res = cls(port, baudrate, protocol_factory)
        await res.reset()
        return res


async def connect_rpc_client(url: RpcUrl) -> RpcClient:
    """Connect to the server on given URL.

    :param url: RPC URL specifying the server location.
    """
    if url.protocol is RpcProtocol.TCP:
        return await RpcClientTCP.connect(url.location, url.port, RpcProtocolStream)
    if url.protocol is RpcProtocol.TCPS:
        return await RpcClientTCP.connect(url.location, url.port, RpcProtocolSerial)
    # TODO SSL and SSLS
    if url.protocol is RpcProtocol.UNIX:
        return await RpcClientUnix.connect(url.location, RpcProtocolStream)
    if url.protocol is RpcProtocol.UNIXS:
        return await RpcClientUnix.connect(url.location, RpcProtocolSerial)
    if url.protocol is RpcProtocol.SERIAL:
        return await RpcClientTTY.open(url.location, url.baudrate, RpcProtocolSerial)
    raise NotImplementedError(f"Unimplemented protocol: {url.protocol}")
