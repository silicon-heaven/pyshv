"""RPC server that waits for clients connection."""
from __future__ import annotations

import abc
import asyncio
import collections.abc
import logging
import pathlib
import typing

import asyncinotify

from . import rpcprotocol
from .rpcclient import RpcClient, RpcClientTTY
from .rpcprotocol import (
    RpcProtocolSerial,
    RpcProtocolSerialCRC,
    RpcProtocolStream,
    RpcTransportProtocol,
)
from .rpcurl import RpcProtocol, RpcUrl

logger = logging.getLogger(__name__)


class RpcServer(abc.ABC):
    """RPC server listening for new SHV connections."""

    @abc.abstractmethod
    def is_serving(self) -> bool:
        """Check if server is accepting new SHV connections."""

    @abc.abstractmethod
    async def listen(self) -> None:
        """Start accepting new SHV connections."""

    @abc.abstractmethod
    async def listen_forewer(self) -> None:
        """Listen and block the calling coroutine until cancelation."""

    @abc.abstractmethod
    def close(self) -> None:
        """Stop accepting new SHV connections."""

    @abc.abstractmethod
    async def wait_closed(self) -> None:
        """Stop accepting new SHV connections and for that to make effect."""


class _RpcServerStream(RpcServer):
    """RPC server listenting for SHV connections for streams."""

    def __init__(
        self,
        client_connected_cb: typing.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        protocol_factory: typing.Type[RpcTransportProtocol] = RpcProtocolStream,
    ):
        self.client_connected_cb = client_connected_cb
        """Callbact that is called when new client is connected."""
        self.protocol_factory = protocol_factory
        """Protocol factory used to create protocol for new clients."""
        self.clients: list[_RpcServerStream.Client] = []
        """List of clients used for termination of the server."""
        self._server: asyncio.Server | None = None

    @abc.abstractmethod
    async def _create_server(self) -> asyncio.Server:
        """Create the server instance."""

    def is_serving(self) -> bool:
        return self._server is not None and self._server.is_serving()

    async def listen(self) -> None:
        if self._server is None:
            self._server = await self._create_server()
        await self._server.start_serving()

    async def listen_forewer(self) -> None:
        if self._server is None:
            self._server = await self._create_server()
        await self._server.serve_forever()

    async def _client_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        client = self.Client(reader, writer, self)
        self.clients.append(client)
        res = self.client_connected_cb(client)
        if isinstance(res, collections.abc.Awaitable):
            await res

    def close(self) -> None:
        if self._server is not None:
            self._server.close()

    async def wait_closed(self) -> None:
        if self._server is not None:
            await self._server.wait_closed()

    class Client(RpcClient):
        """RPC client for Asyncio's stream server connection."""

        def __init__(
            self,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
            server: _RpcServerStream,
        ) -> None:
            super().__init__()
            self._reader = reader
            self._writer = writer
            self._protocol = rpcprotocol.protocol_for_asyncio_stream(
                server.protocol_factory, reader, writer
            )

        async def _send(self, msg: bytes) -> None:
            await self._protocol.send(msg)

        async def _receive(self) -> bytes:
            return await self._protocol.receive()

        @property
        def connected(self) -> bool:
            return not self._writer.is_closing()

        async def reset(self) -> bool:
            self.disconnect()
            return False

        def disconnect(self) -> None:
            self._writer.close()

        async def wait_disconnect(self) -> None:
            await self._writer.wait_closed()


class RpcServerTCP(_RpcServerStream):
    """RPC server listenting for SHV connections in TCP/IP."""

    def __init__(
        self,
        client_connected_cb: typing.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        location: str | None = None,
        port: int = 3755,
        protocol_factory: typing.Type[RpcTransportProtocol] = RpcProtocolStream,
    ):
        super().__init__(client_connected_cb, protocol_factory)
        self.location = location
        self.port = port

    async def _create_server(self) -> asyncio.Server:
        return await asyncio.start_server(
            self._client_connect, host=self.location, port=self.port
        )

    async def listen(self) -> None:
        was_listening = self.is_serving()
        await super().listen()
        if not was_listening:
            logger.debug("Listening for clients: (TCP) %s:%d", self.location, self.port)

    def close(self) -> None:
        was_listening = self.is_serving()
        super().close()
        if was_listening and (self._server is None or not self._server.is_serving()):
            logger.debug(
                "No longer listening for clients: (TCP) %s:%d", self.location, self.port
            )

    async def _client_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peername = writer.get_extra_info("peername")
        logger.debug(
            "New client: (TCP) %s:%d: %s:%d",
            self.location,
            self.port,
            peername[0],
            peername[1],
        )
        await super()._client_connect(reader, writer)


class RpcServerUnix(_RpcServerStream):
    """RPC server listenting for SHV connections on Unix domain named socket."""

    def __init__(
        self,
        client_connected_cb: typing.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        location: str = "shv.sock",
        protocol_factory: typing.Type[RpcTransportProtocol] = RpcProtocolStream,
    ):
        super().__init__(client_connected_cb, protocol_factory)
        self.location = location

    async def _create_server(self) -> asyncio.Server:
        return await asyncio.start_unix_server(self._client_connect, path=self.location)

    async def listen(self) -> None:
        was_listening = self.is_serving()
        await super().listen()
        if not was_listening:
            logger.debug("Listening for clients: (Unix) %s", self.location)

    def close(self) -> None:
        was_listening = self.is_serving()
        super().close()
        if was_listening and (self._server is None or self._server.is_serving()):
            logger.debug("No longer listening for clients: (Unix) %s", self.location)

    async def _client_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        logger.debug(
            "New client: (Unix) %s: %s",
            self.location,
            writer.get_extra_info("peername"),
        )
        await super()._client_connect(reader, writer)


class RpcServerTTY(RpcServer):
    """RPC server waiting for TTY to appear.

    This actually only maintains a single client as there can't be more than one
    client on single TTY.
    """

    def __init__(
        self,
        client_connected_cb: typing.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        port: str,
        baudrate: int = 115200,
        protocol_factory: typing.Type[RpcTransportProtocol] = RpcProtocolSerialCRC,
    ):
        self.client_connected_cb = client_connected_cb
        """Callbact that is called when new client is connected."""
        self.client = RpcClientTTY(port, baudrate, protocol_factory)
        """The :class:`RpcClientTTY` instance."""
        self._task: asyncio.Task | None = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.client.reset()
            except OSError as exc:
                logger.debug("Waiting for accessible TTY device: %s", exc)
            else:
                res = self.client_connected_cb(self.client)
                if isinstance(res, collections.abc.Awaitable):
                    await res
                await self.client.wait_disconnect()
                continue
            with asyncinotify.Inotify() as inotify:
                pth = pathlib.Path(self.client.port)
                inotify.add_watch(
                    pth.parent, asyncinotify.Mask.CREATE | asyncinotify.Mask.ATTRIB
                )
                async for event in inotify:
                    if str(pth.name) == str(event.name):
                        break

    def is_serving(self) -> bool:
        return self._task is not None and not self._task.done()

    async def listen(self) -> None:
        if not self.is_serving():
            self._task = asyncio.create_task(self._loop())

    async def listen_forewer(self) -> None:
        await self.listen()
        await self.wait_closed()

    def close(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def wait_closed(self) -> None:
        if self._task is not None:
            await self._task


async def create_rpc_server(
    client_connected_cb: typing.Callable[
        [RpcClient], None | collections.abc.Awaitable[None]
    ],
    url: RpcUrl,
) -> RpcServer:
    """Create server listening on given URL.

    :param client_connected_cb: function called for every new client connected.
    :param url: RPC URL specifying where server should listen.
    """
    res: RpcServer
    if url.protocol is RpcProtocol.TCP:
        res = RpcServerTCP(
            client_connected_cb, url.location, url.port, RpcProtocolStream
        )
    elif url.protocol is RpcProtocol.TCPS:
        res = RpcServerTCP(
            client_connected_cb, url.location, url.port, RpcProtocolSerial
        )
    elif url.protocol is RpcProtocol.UNIX:
        res = RpcServerUnix(client_connected_cb, url.location, RpcProtocolStream)
    elif url.protocol is RpcProtocol.UNIXS:
        res = RpcServerUnix(client_connected_cb, url.location, RpcProtocolSerial)
    elif url.protocol is RpcProtocol.SERIAL:
        res = RpcServerTTY(
            client_connected_cb, url.location, url.baudrate, RpcProtocolSerialCRC
        )
    else:
        raise NotImplementedError(f"Unimplemented protocol: {url.protocol}")
    await res.listen()
    return res
