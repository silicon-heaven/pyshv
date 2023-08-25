"""RPC server that waits for clients connection."""
import abc
import asyncio
import collections.abc
import contextlib
import functools
import logging
import typing

from .chainpack import ChainPack
from .rpcclient import RpcClient, RpcClientStream
from .rpcmessage import RpcMessage
from .rpcurl import RpcProtocol, RpcUrl

logger = logging.getLogger(__name__)


class RpcServer(abc.ABC):
    """RPC server listening for new SHV connections."""

    @abc.abstractmethod
    def close(self) -> None:
        """Stop accepting new SHV connections."""

    async def wait_closed(self) -> None:
        """Wait for close to be actually performed."""


class RpcServerStream(RpcServer):
    """RPC server listening for new SHV connections on stream transport layer."""

    def __init__(
        self,
        client_connected_cb: typing.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        loop: asyncio.events.AbstractEventLoop,
        get_server: typing.Callable,  # @TODO
        wait_listening: asyncio.Future,
    ):
        """Do not initialize this object directly, use :meth:`tcp_listen` or
        :meth:`unix_listen` instead.
        """
        self._client_connected_cb = client_connected_cb
        self._server: asyncio.Server | None = None
        self._task = loop.create_task(self._serve(get_server, wait_listening))

    async def _serve(
        self,
        get_server,
        wait_listening: asyncio.Future,
    ) -> None:
        self._server = await get_server(self._client_connect)
        assert self._server is not None
        wait_listening.set_result(self._server)
        await self._server.serve_forever()

    async def _client_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        client = RpcClientStream(reader, writer)
        res = self._client_connected_cb(client)
        if isinstance(res, collections.abc.Awaitable):
            await res

    @classmethod
    async def listen(
        cls,
        client_connected_cb: typing.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        location: str,
        port: int,
    ) -> "RpcServerStream":
        """Start listening on given address and port for TCP connections.

        :param client_connected_cb: Function called for every new connected client.
        :param location: IP/Hostname
        :param port: Listening port
        :return: Handle used to control the listening server.
        """
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        res = cls(
            client_connected_cb,
            loop,
            functools.partial(asyncio.start_server, host=location, port=port),
            future,
        )
        await future
        return res

    @classmethod
    async def unix_listen(
        cls,
        client_connected_cb: typing.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        path: str,
    ) -> "RpcServerStream":
        """Start listening on given address and port for local socket connections.

        :param client_connected_cb: Function called for every new connected client.
        :param path: Path to the Unix domain socket.
        :return: Handle used to control the listening server.
        """
        # TODO try to remove socket on server stop
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        res = cls(
            client_connected_cb,
            loop,
            functools.partial(asyncio.start_unix_server, path=path),
            future,
        )
        await future
        return res

    def close(self) -> None:
        assert self._server is not None
        self._server.close()

    async def wait_closed(self) -> None:
        assert self._server is not None
        await self._server.wait_closed()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task


class RpcServerDatagram(RpcServer):
    """RPC server listening for new SHV connections on datagram transport layer."""

    class _RpcClientDatagramServer(RpcClient):
        def __init__(
            self,
            addr: str,
            protocol: "RpcServerDatagram._Protocol",
        ) -> None:
            super().__init__()
            self._addr = addr
            self._protocol = protocol

        async def send(self, msg: RpcMessage) -> None:
            await super().send(msg)
            self._protocol.transport.sendto(
                bytes((ChainPack.ProtocolType,)) + msg.to_chainpack(), self._addr
            )

        async def _receive(self) -> bytes | None:
            queue = self._protocol.existing_clients.get(self._addr, None)
            if queue is None:
                return None
            data = await queue.get()
            queue.task_done()
            return data

        async def _reset(self) -> None:
            self._protocol.transport._sock.sendto(bytes(), self._addr)  # type: ignore

        def connected(self) -> bool:
            return self._addr in self._protocol.existing_clients

        async def disconnect(self) -> None:
            if self._addr in self._protocol.existing_clients:
                await self._protocol.existing_clients[self._addr].put(None)
            self._protocol.existing_clients.pop(self._addr, None)
            if not self._protocol.existing_clients and not self._protocol.accept_new:
                self._protocol.transport.close()

    class _Protocol(asyncio.DatagramProtocol):
        """Implementation of Asyncio datagram protocol to listen on UDP."""

        def __init__(
            self,
            new_client_cb: typing.Callable[
                [RpcClient], None | collections.abc.Awaitable[None]
            ],
        ):
            self.new_client_cb = new_client_cb
            self.existing_clients: dict[str, asyncio.Queue] = {}
            self.transport: asyncio.DatagramTransport
            self.accept_new: bool = True
            self._loop = asyncio.get_running_loop()

        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            if not data or addr not in self.existing_clients:
                if not self.accept_new:
                    return
                self.existing_clients[addr] = asyncio.Queue()
                res = self.new_client_cb(
                    RpcServerDatagram._RpcClientDatagramServer(addr, self)
                )
                if asyncio.iscoroutine(res):
                    self._loop.create_task(res)
            if data:
                self.existing_clients[addr].put_nowait(data)

    def __init__(
        self,
        transport: asyncio.DatagramTransport,
        protocol: _Protocol,
    ):
        """Do not initialize this directly, use :func:`create_rpc_server` instead."""
        self._transport = transport
        self._protocol = protocol
        self._close = asyncio.get_running_loop().create_future()

    @classmethod
    async def listen(
        cls,
        client_connected_cb: typing.Callable[
            [RpcClient], None | collections.abc.Awaitable[None]
        ],
        location: str,
        port: int,
    ) -> "RpcServerDatagram":
        """Start listening on given address and port for TCP connections.

        :param client_connected_cb: Function called for every new connected client.
        :param location: IP/Hostname
        :param port: Listening port
        :return: Handle used to control the listening server.
        """
        t, p = await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: cls._Protocol(client_connected_cb),
            local_addr=(location or "localhost", port),
        )
        return cls(t, p)

    def close(self) -> None:
        """Stop accepting new SHV connections.

        Be aware that compared with TCP/IP this won't immediately free the port for
        listening. The listening socket is actually closed only when server stops
        listening for a new connections and all clients are disconnected.
        """
        self._protocol.accept_new = False
        if not self._protocol.existing_clients:
            self._transport.close()
        if not self._close.done():
            self._close.set_result(None)

    async def wait_closed(self) -> None:
        await self._close


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
    if url.protocol is RpcProtocol.TCP:
        return await RpcServerStream.listen(client_connected_cb, url.location, url.port)
    if url.protocol is RpcProtocol.LOCAL_SOCKET:
        return await RpcServerStream.unix_listen(client_connected_cb, url.location)
    if url.protocol is RpcProtocol.UDP:
        return await RpcServerDatagram.listen(
            client_connected_cb, url.location, url.port
        )
    raise NotImplementedError(f"Unimplemented protocol: {url.protocol}")
