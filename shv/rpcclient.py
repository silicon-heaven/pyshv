"""RPC connection, that includes client and specific server connection."""

from __future__ import annotations

import abc
import asyncio
import contextlib
import enum
import logging
import os
import time
import typing

import aioserial

from .chainpack import ChainPack
from .rpcmessage import RpcMessage
from .rpcprotocol import (
    RpcProtocolSerial,
    RpcProtocolSerialCRC,
    RpcProtocolStream,
    RpcTransportProtocol,
)
from .rpcurl import RpcProtocol, RpcUrl
from .value import SHVIMap

logger = logging.getLogger(__name__)


class RpcClient(abc.ABC):
    """RPC connection to some SHV peer."""

    class Control(enum.Enum):
        """Control message that is received instead of :class:`RpcMessage`."""

        RESET = enum.auto()

    def __init__(self) -> None:
        self.last_send = time.monotonic()
        """Monotonic time when last message was sent on this connection.

        The initial value is time of the RpcClient creation.
        """
        self.last_receive = time.monotonic()
        """Monotonic time when last message was received on this connection.

        The initial value is time of the RpcClient creation.
        """

    @classmethod
    async def connect(cls, *args: typing.Any, **kwargs: typing.Any) -> typing.Self:  # noqa ANN401
        """Connect client.

        This conveniently combines object initialization and call to
        :meth:`reset`. All arguments are passed to the object initialization.
        """
        res = cls(*args, **kwargs)
        await res.reset()
        return res

    async def send(self, msg: RpcMessage) -> None:
        """Send the given SHV RPC Message.

        :param msg: Message to be sent
        :raise EOFError: when client is not connected.
        """
        await self._send(bytearray((ChainPack.ProtocolType,)) + msg.to_chainpack())
        self.last_send = time.monotonic()
        logger.debug("%s => %s", str(self), msg.to_string())

    @abc.abstractmethod
    async def _send(self, msg: bytes) -> None:
        """Child's implementation of message sending."""

    async def receive(self, raise_error: bool = True) -> RpcMessage | Control:
        """Read next received RPC message or wait for next to be received.

        :param raise_error: If RpcError should be raised or not.
        :return: Next RPC message is returned or :class:`Control` for special control
          messages.
        :raise RpcError: When mesasge is error and ``raise_error`` is `True`.
        :raise EOFError: in case EOF is encountered.
        """
        while True:
            data = await self._receive()
            self.last_receive = time.monotonic()
            if len(data) > 1:
                if data[0] == ChainPack.ProtocolType:
                    try:
                        shvdata = ChainPack.unpack(data[1:])
                    except ValueError:
                        pass
                    else:
                        if isinstance(shvdata, SHVIMap):
                            msg = RpcMessage(shvdata)
                            logger.debug("%s <= %s", self, msg.to_string())
                            if raise_error and msg.is_error:
                                raise msg.rpc_error
                            return msg
            elif len(data) == 1 and data[0] == 0:
                logger.debug("%s <= Control message RESET", self)
                return self.Control.RESET
            logger.debug("%s <= Invalid message received: %s", self, data)

    @abc.abstractmethod
    async def _receive(self) -> bytes:
        """Message receive implementation.

        :return: bytes of received message (complete valid message).
        :raise EOFError: if end of the connection is encountered.
        """

    async def reset(self) -> None:
        """Reset the connection.

        This sends reset to the peer and thus it is instructed to forget anything that
        might have been associated with this client.

        This can also try reconnect if client supports it.

        This can raise not only :class:`EOFError` but also other exception based
        on the client implementation.

        :raise EOFError: if peer is not connected and reconnect is not either supported
          or possible.
        """
        await self._send(bytes((0,)))
        logger.debug("%s => Control message RESET")

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

    def disconnect(self) -> None:
        """Close the connection."""
        if self.connected:
            logger.debug("%s: Disconnecting", self)
        self._disconnect()

    @abc.abstractmethod
    def _disconnect(self) -> None:
        """Child's implementation of message sending."""

    async def wait_disconnect(self) -> None:  # noqa D027
        """Close the connection."""


class _RpcClientStream(RpcClient):
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
        return self._writer is not None and not self._writer.is_closing()

    def _disconnect(self) -> None:
        if self._writer is not None:
            self._writer.close()

    async def wait_disconnect(self) -> None:
        if self._writer is not None:
            with contextlib.suppress(ConnectionError):
                await self._writer.wait_closed()


class RpcClientTCP(_RpcClientStream):
    """RPC connection to some SHV peer over TCP/IP."""

    def __init__(
        self,
        location: str = "localhost",
        port: int = 3755,
        protocol: type[RpcTransportProtocol] = RpcProtocolStream,
    ) -> None:
        super().__init__(protocol)
        self.location = location
        self.port = port

    def __str__(self) -> str:
        location = f"[{self.location}]" if ":" in self.location else self.location
        return f"tcp:{location}:{self.port}"

    async def _open_connection(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.open_connection(self.location, self.port)


class RpcClientUnix(_RpcClientStream):
    """RPC connection to some SHV peer over Unix domain named socket."""

    def __init__(
        self,
        location: str = "shv.sock",
        protocol: type[RpcTransportProtocol] = RpcProtocolSerial,
    ) -> None:
        super().__init__(protocol)
        self.location = location

    def __str__(self) -> str:
        return f"unix:{self.location}"

    async def _open_connection(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.open_unix_connection(self.location)


class RpcClientPipe(_RpcClientStream):
    """RPC connection to some SHV peer over Unix pipes or other such streams."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        protocol: type[RpcTransportProtocol] = RpcProtocolSerial,
    ) -> None:
        super().__init__(protocol)
        self._reader = reader
        self._writer = writer

    def __str__(self) -> str:
        return "pipe"

    async def _open_connection(  # noqa PLR6301
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        raise ConnectionError("Pipes can't be reconnected")

    @classmethod
    async def fdopen(
        cls,
        rpipe: int | typing.IO,
        wpipe: int | typing.IO,
        protocol: type[RpcTransportProtocol] = RpcProtocolSerial,
    ) -> RpcClientPipe:
        """Create RPC client from existing Unix pipes."""
        if isinstance(rpipe, int):
            rpipe = os.fdopen(rpipe, mode="r")
        reader = asyncio.StreamReader()
        srprotocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_running_loop().connect_read_pipe(lambda: srprotocol, rpipe)

        if isinstance(wpipe, int):
            wpipe = os.fdopen(wpipe, mode="w")
        wtransport, _ = await asyncio.get_running_loop().connect_write_pipe(
            lambda: srprotocol, wpipe
        )
        writer = asyncio.StreamWriter(
            wtransport, srprotocol, None, asyncio.get_running_loop()
        )

        return cls(reader, writer, protocol)

    @classmethod
    async def open_pair(
        cls,
        protocol: type[RpcTransportProtocol] = RpcProtocolSerial,
        flags: int = 0,
    ) -> tuple[RpcClientPipe, RpcClientPipe]:
        """Create pair of clients that are interconnected over the pipe.

        :param protocol: The protocol factory to be used.
        :param flags: Flags passed to :meth:`os.pipe2`.
        :return: Pair of clients that are interconnected over Unix pipes.
        """
        pr1, pw1 = os.pipe2(flags)
        pr2, pw2 = os.pipe2(flags)
        client1 = await cls.fdopen(pr1, pw2, protocol)
        client2 = await cls.fdopen(pr2, pw1, protocol)
        return client1, client2


class RpcClientTTY(RpcClient):
    """RPC connection to some SHV peer over Unix domain named socket."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        protocol: type[RpcTransportProtocol] = RpcProtocolSerialCRC,
    ) -> None:
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.protocol = protocol
        self.serial: None | aioserial.AioSerial = None
        self._eof = asyncio.Event()
        self._eof.set()

    def __str__(self) -> str:
        return f"tty:{self.port}"

    async def _send(self, msg: bytes) -> None:
        await self.protocol.send(self._write_async, msg)

    async def _receive(self) -> bytes:
        return await self.protocol.receive(self._read_exactly)

    @property
    def connected(self) -> bool:  # noqa: D102
        return self.serial is not None and self.serial.is_open

    async def reset(self) -> None:  # noqa: D102
        if not self.connected:
            self.serial = aioserial.AioSerial(
                port=self.port,
                baudrate=self.baudrate,
                rtscts=True,
                dsrdtr=True,
                exclusive=True,
            )
            self._eof.clear()
            logger.debug("%s: Connected", self)
        await super().reset()

    async def _write_async(self, data: bytes) -> None:
        assert self.serial is not None
        await self.serial.write_async(data)

    async def _read_exactly(self, n: int) -> bytes:
        assert self.serial is not None
        res = bytearray()
        while len(res) < n:
            try:
                res += await self.serial.read_async(n - len(res))
            except aioserial.SerialException as exc:
                self._eof.set()
                raise EOFError from exc
        return res

    def _disconnect(self) -> None:
        if self.connected:
            assert self.serial is not None
            self.serial.close()
            self._eof.set()

    async def wait_disconnect(self) -> None:  # noqa: D102
        await self._eof.wait()


def init_rpc_client(url: RpcUrl) -> RpcClient:
    """Initialize correct :class:`RpcClient` for given URL.

    :param url: RPC URL specifying the connection target.
    :return: Chosen :class:`RpcClient` child instance based on the passed URL.
    """
    match url.protocol:
        case RpcProtocol.TCP:
            return RpcClientTCP(url.location, url.port, RpcProtocolStream)
        case RpcProtocol.TCPS:
            return RpcClientTCP(url.location, url.port, RpcProtocolSerial)
        case RpcProtocol.UNIX:
            return RpcClientUnix(url.location, RpcProtocolStream)
        case RpcProtocol.UNIXS:
            return RpcClientUnix(url.location, RpcProtocolSerial)
        case RpcProtocol.SERIAL:
            return RpcClientTTY(url.location, url.baudrate, RpcProtocolSerialCRC)
        case _:
            raise NotImplementedError(f"Unimplemented protocol: {url.protocol}")


async def connect_rpc_client(url: RpcUrl) -> RpcClient:
    """Initialize and establish :class:`RpcClient` connection for given URL.

    Compared to the :func:`init_rpc_client` this also calls
    :meth:`RpcClient.reset` to establish the connection.

    :param url: RPC URL specifying the connection target.
    :return: Chosen :class:`RpcClient` child instance based on the passed URL.
    """
    res = init_rpc_client(url)
    await res.reset()
    return res
