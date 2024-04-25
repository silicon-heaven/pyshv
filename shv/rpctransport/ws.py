"""Connection over WebSockets."""

from __future__ import annotations

import abc
import asyncio
import collections.abc
import logging
import typing

import websockets.client
import websockets.server

from .abc import RpcClient, RpcServer

logger = logging.getLogger(__name__)


class RpcClientWebSockets(RpcClient):
    """RPC connection to some SHV peer over WebSockets.

    :param uri: URI for the websocket connection.
    :param location: This is either hostname and path for the host connection or
      path to the Unix socket.
    :param port: Port used when connecting to the host. Keep it to ``-1`` if you
      are connecting to the Unix socket.
    """

    def __init__(self, location: str, port: int = -1) -> None:
        super().__init__()
        self.location = location
        self.port = port
        self._wsp: websockets.client.WebSocketClientProtocol | None = None
        self._close_task: asyncio.Task | None = None

    def __str__(self) -> str:
        if self.port == -1:
            return f"ws:{self.location}"
        return f"ws:{self.location}:{self.port}"

    async def _send(self, msg: bytes) -> None:
        if self._wsp is None:
            raise EOFError("Not connected")
        try:
            await self._wsp.send(msg)
        except (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.ConnectionClosedOK,
            websockets.exceptions.ConnectionClosedError,
        ) as exc:
            raise EOFError from exc

    async def _receive(self) -> bytes:
        if self._wsp is None:
            raise EOFError("Not connected")
        try:
            # Ignore case when text frame is send to us for what ever reason.
            while True:
                if isinstance(res := await self._wsp.recv(), bytes):
                    return res
        except (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.ConnectionClosedOK,
            websockets.exceptions.ConnectionClosedError,
        ) as exc:
            raise EOFError from exc

    async def reset(self) -> None:
        """Reset or establish the connection.

        This method not only resets the existing connection but primarilly
        estableshes the new one.
        """
        if not self.connected:
            if self.port != -1:
                self._wsp = await websockets.client.connect(
                    f"ws://{self.location}:{self.port}"
                )
            else:
                self._wsp = await websockets.client.unix_connect(self.location)
            self._close_task = None
            logger.debug("%s: Connected", self)
        else:
            await super().reset()

    @property
    def connected(self) -> bool:
        """Check if client is still connected."""
        return self._wsp is not None and self._wsp.open

    def _disconnect(self) -> None:
        if self._close_task is None and self._wsp is not None:
            self._close_task = asyncio.create_task(self._wsp.close())

    async def wait_disconnect(self) -> None:
        """Wait for the client's disconnection."""
        if self._wsp is not None:
            await self._wsp.wait_closed()
            if self._close_task is not None:
                await self._close_task


# TODO possibly implement RpcClientWebsocketsUnix if uri can't specify unix
# connection


class _RpcServerWebSockets(RpcServer):
    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
    ) -> None:
        self.client_connected_cb = client_connected_cb
        """Callbact that is called when new client is connected."""
        self._server: websockets.server.WebSocketServer | None = None

    @abc.abstractmethod
    async def _create_server(self) -> websockets.server.WebSocketServer:
        pass

    async def _client_connect(
        self, wsp: websockets.server.WebSocketServerProtocol
    ) -> None:
        res = self.client_connected_cb(self.Client(wsp, self))
        if isinstance(res, collections.abc.Awaitable):
            await res
        await wsp.wait_closed()

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

    def close(self) -> None:
        if self._server is not None:
            self._server.close()

    async def wait_closed(self) -> None:
        if self._server is not None:
            await self._server.wait_closed()

    class Client(RpcClient):
        def __init__(
            self,
            wsp: websockets.server.WebSocketServerProtocol,
            server: _RpcServerWebSockets,
        ) -> None:
            super().__init__()
            self.wsp = wsp
            self._close_task: asyncio.Task | None = None
            self._server = server

        async def _send(self, msg: bytes) -> None:
            try:
                await self.wsp.send(msg)
            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedOK,
                websockets.exceptions.ConnectionClosedError,
            ) as exc:
                raise EOFError from exc

        async def _receive(self) -> bytes:
            try:
                # Ignore case when text frame is send to us for what ever reason.
                while True:
                    if isinstance(res := await self.wsp.recv(), bytes):
                        return res
            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedOK,
                websockets.exceptions.ConnectionClosedError,
            ) as exc:
                raise EOFError from exc

        @property
        def connected(self) -> bool:
            # We are using not closed because open is false in the initial
            # connection phase.
            return not self.wsp.closed

        def _disconnect(self) -> None:
            if self._close_task is None and self.wsp is not None:
                self._close_task = asyncio.create_task(self.wsp.close())

        async def wait_disconnect(self) -> None:
            if self.wsp is not None:
                await self.wsp.wait_closed()
                if self._close_task is not None:
                    await self._close_task


class RpcServerWebSockets(_RpcServerWebSockets):
    """RPC server listening for WebSockets connections.

    :param client_connected_cb: Callback called when new connection is received.
    :param location: Hostname or IP address this server should listen on. The
      default ``None`` listens on all addresses.
    :param port: The port servers listens on.
    """

    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        location: str | None = None,
        port: int = 8001,
    ) -> None:
        super().__init__(client_connected_cb)
        self.location = location
        """Host websockets server should listen on."""
        self.port = port
        """Port websocket server should listen on."""

    async def _create_server(self) -> websockets.server.WebSocketServer:
        return await websockets.server.serve(
            self._client_connect, self.location, self.port, start_serving=False
        )

    def __str__(self) -> str:
        location = (
            "locahost"
            if self.location is None
            else f"[{self.location}]"
            if ":" in self.location
            else self.location
        )
        return f"server.ws:{location}:{self.port}"

    class Client(_RpcServerWebSockets.Client):
        """RPC client for WebSockets server connection."""

        def __str__(self) -> str:
            address = self.wsp.remote_address
            location = f"[{address[0]}]" if ":" in address[0] else address[0]
            return f"ws:{location}:{address[1]}"


class RpcServerWebSocketsUnix(_RpcServerWebSockets):
    """RPC server listening for WebSockets connections on Unix socket.

    :param client_connected_cb: Callback called when new connection is received.
    :param location: Path where Unix socket will be created and server will
      listen on.
    """

    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        location: str,
    ) -> None:
        super().__init__(client_connected_cb)
        self.location = location
        """Path to Unix socket server should listen on."""

    async def _create_server(self) -> websockets.server.WebSocketServer:
        return await websockets.server.unix_serve(self._client_connect, self.location)

    def __str__(self) -> str:
        return f"server.ws:{self.location}"

    class Client(_RpcServerWebSockets.Client):
        """RPC client for WebSockets server over Unix socket connection."""

        def __str__(self) -> str:
            return f"server.ws:{typing.cast(RpcServerWebSocketsUnix, self._server).location}"
