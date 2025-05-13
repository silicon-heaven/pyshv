"""Connection over WebSockets."""

from __future__ import annotations

import abc
import asyncio
import collections.abc
import logging
import typing
import weakref

import websockets.asyncio.client
import websockets.asyncio.server
import websockets.exceptions
import websockets.typing

from .abc import RpcClient, RpcServer

logger = logging.getLogger(__name__)

subprotocol = websockets.typing.Subprotocol("shv3")


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
        self._wsp: websockets.asyncio.client.ClientConnection | None = None
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
                self._wsp = await websockets.asyncio.client.connect(
                    f"ws://{self.location}:{self.port}", subprotocols=[subprotocol]
                )
            else:
                self._wsp = await websockets.asyncio.client.unix_connect(
                    self.location, subprotocols=[subprotocol]
                )
            if self._wsp.subprotocol != subprotocol:
                real_subprotocol = self._wsp.subprotocol
                await self._wsp.close()
                self._wsp = None
                raise websockets.exceptions.InvalidHandshake(
                    f"Unexpected subprotocol: {real_subprotocol}"
                )
            self._close_task = None
            logger.debug("%s: Connected", self)
        else:
            await super().reset()

    @property
    def connected(self) -> bool:
        """Check if client is still connected."""
        return self._wsp is not None and self._wsp.state in {
            websockets.protocol.State.CONNECTING,
            websockets.protocol.State.OPEN,
        }

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
            [RpcClient], collections.abc.Awaitable[None] | None
        ],
    ) -> None:
        self.client_connected_cb = client_connected_cb
        """Callback that is called when new client is connected."""
        self._server: websockets.asyncio.server.Server | None = None
        self._clients: weakref.WeakSet[_RpcServerWebSockets.Client] = weakref.WeakSet()

    @abc.abstractmethod
    async def _create_server(self) -> websockets.asyncio.server.Server:
        pass

    async def _client_connect(
        self, wsp: websockets.asyncio.server.ServerConnection
    ) -> None:
        client = self.Client(wsp, self)
        self._clients.add(client)
        res = self.client_connected_cb(client)
        if isinstance(res, collections.abc.Awaitable):
            await res
        # This coroutine must be blocked to not close the connection.
        await client.wait_disconnect()

    def is_serving(self) -> bool:
        return self._server is not None and self._server.is_serving()

    async def listen(self) -> None:
        if self._server is None:
            self._server = await self._create_server()
        # Note: server starts listening automatically

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

    def terminate(self) -> None:
        self.close()
        for client in self._clients:
            client.disconnect()

    async def wait_terminated(self) -> None:
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
        def __init__(
            self,
            wsp: websockets.asyncio.server.ServerConnection,
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
            return self.wsp.state in {
                websockets.protocol.State.CONNECTING,
                websockets.protocol.State.OPEN,
            }

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
            [RpcClient], collections.abc.Awaitable[None] | None
        ],
        location: str | None = None,
        port: int = 8001,
    ) -> None:
        super().__init__(client_connected_cb)
        self.location = location
        """Host websockets server should listen on."""
        self.port = port
        """Port websocket server should listen on."""

    async def _create_server(self) -> websockets.asyncio.server.Server:
        return await websockets.asyncio.server.serve(
            self._client_connect,
            self.location,
            self.port,
            subprotocols=[subprotocol],
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
            [RpcClient], collections.abc.Awaitable[None] | None
        ],
        location: str,
    ) -> None:
        super().__init__(client_connected_cb)
        self.location = location
        """Path to Unix socket server should listen on."""

    async def _create_server(self) -> websockets.asyncio.server.Server:
        return await websockets.asyncio.server.unix_serve(
            self._client_connect,
            self.location,
            subprotocols=[subprotocol],
        )

    def __str__(self) -> str:
        return f"server.ws:{self.location}"

    class Client(_RpcServerWebSockets.Client):
        """RPC client for WebSockets server over Unix socket connection."""

        def __str__(self) -> str:
            return f"server.ws:{typing.cast(RpcServerWebSocketsUnix, self._server).location}"
