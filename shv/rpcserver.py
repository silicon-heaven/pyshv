"""RPC server that waits for clients connection."""

from __future__ import annotations

import abc
import asyncio
import collections.abc
import contextlib
import logging
import pathlib
import typing

try:
    import asyncinotify
except (ImportError, TypeError):  # pragma: no cover
    asyncinotify = None  # type: ignore

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
        protocol: type[RpcTransportProtocol] = RpcProtocolStream,
    ) -> None:
        self.client_connected_cb = client_connected_cb
        """Callbact that is called when new client is connected."""
        self.protocol = protocol
        """Stream communication protocol."""
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
            return not self._writer.is_closing()

        def _disconnect(self) -> None:
            self._writer.close()

        async def wait_disconnect(self) -> None:
            with contextlib.suppress(ConnectionError):
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
        protocol: type[RpcTransportProtocol] = RpcProtocolStream,
    ) -> None:
        super().__init__(client_connected_cb, protocol)
        self.location = location
        self.port = port

    def __str__(self) -> str:
        location = (
            "locahost"
            if self.location is None
            else f"[{self.location}]"
            if ":" in self.location
            else self.location
        )
        return f"server.tcp:{location}:{self.port}"

    async def _create_server(self) -> asyncio.Server:
        return await asyncio.start_server(
            self._client_connect, host=self.location, port=self.port
        )

    async def listen(self) -> None:  # noqa: D102
        was_listening = self.is_serving()
        await super().listen()
        if not was_listening:
            logger.debug("%s: Listening for clients", self)

    def close(self) -> None:  # noqa: D102
        was_listening = self.is_serving()
        super().close()
        if was_listening and (self._server is None or not self._server.is_serving()):
            logger.debug("%s: No longer listening for clients", self)

    async def _client_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peername = writer.get_extra_info("peername")
        location = f"[{peername[0]}]" if ":" in peername[0] else peername[0]
        logger.debug("%s: New client %s:%d", self, location, peername[1])
        await super()._client_connect(reader, writer)

    class Client(_RpcServerStream.Client):
        """RPC client for TCP server connection."""

        def __str__(self) -> str:
            peername = self._writer.get_extra_info("peername")
            location = f"[{peername[0]}]" if ":" in peername[0] else peername[0]
            return f"tcp:{location}:{peername[1]}"


class RpcServerUnix(_RpcServerStream):
    """RPC server listenting for SHV connections on Unix domain named socket."""

    def __init__(
        self,
        client_connected_cb: typing.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        location: str = "shv.sock",
        protocol: type[RpcTransportProtocol] = RpcProtocolSerial,
    ) -> None:
        super().__init__(client_connected_cb, protocol)
        self.location = location

    def __str__(self) -> str:
        return f"server.unix:{self.location}"

    async def _create_server(self) -> asyncio.Server:
        return await asyncio.start_unix_server(self._client_connect, path=self.location)

    async def listen(self) -> None:  # noqa: D102
        was_listening = self.is_serving()
        await super().listen()
        if not was_listening:
            logger.debug("%s: Listening for clients", self)

    def close(self) -> None:  # noqa: D102
        was_listening = self.is_serving()
        super().close()
        if was_listening and (self._server is None or self._server.is_serving()):
            logger.debug("%s: No longer listening for clients", self)

    async def _client_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        logger.debug("%s: New client %s", self, writer.get_extra_info("peername"))
        await super()._client_connect(reader, writer)

    class Client(_RpcServerStream.Client):
        """RPC client for Unix server connection."""

        def __str__(self) -> str:
            return f"unix:{self._writer.get_extra_info('peername')}"


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
        protocol: type[RpcTransportProtocol] = RpcProtocolSerialCRC,
    ) -> None:
        self.client_connected_cb = client_connected_cb
        """Callbact that is called when new client is connected."""
        self.client = RpcClientTTY(port, baudrate, protocol)
        """The :class:`RpcClientTTY` instance."""
        self._task: asyncio.Task | None = None

    def __str__(self) -> str:
        return f"tty:{self.client.port}"

    async def _loop(self) -> None:
        while True:
            try:
                await self.client.reset()
            except OSError as exc:
                logger.debug("%s: Waiting for accessible TTY device: %s", self, exc)
            else:
                res = self.client_connected_cb(self.client)
                if isinstance(res, collections.abc.Awaitable):
                    await res
                await self.client.wait_disconnect()
                continue
            if asyncinotify is not None:
                with asyncinotify.Inotify() as inotify:
                    pth = pathlib.Path(self.client.port)
                    inotify.add_watch(
                        pth.parent, asyncinotify.Mask.CREATE | asyncinotify.Mask.ATTRIB
                    )
                    async for event in inotify:
                        if str(pth.name) == str(event.name):
                            break
            else:
                await asyncio.sleep(5)  # type: ignore

    def is_serving(self) -> bool:  # noqa: D102
        return self._task is not None and not self._task.done()

    async def listen(self) -> None:  # noqa: D102
        if not self.is_serving():
            self._task = asyncio.create_task(self._loop())

    async def listen_forewer(self) -> None:  # noqa: D102
        await self.listen()
        await self.wait_closed()

    def close(self) -> None:  # noqa: D102
        if self._task is not None:
            self._task.cancel()

    async def wait_closed(self) -> None:  # noqa: D102
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
