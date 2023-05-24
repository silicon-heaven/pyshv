"""RPC server that waits for clients connection."""
import asyncio
import collections.abc
import logging
import typing

from .rpcclient import RpcClient
from .rpcurl import RpcProtocol

logger = logging.getLogger(__name__)


class RpcServer:
    """RPC server waiting for the client connection.

    :param callback: Function called for the accepted clients
    :param host: Listening IP (TCP) or socket path (LOCAL_SOCKET)
    :param port: Listening port (TCP)
    :param protocol: Protocol used by the server
    """

    def __init__(
        self,
        callback: typing.Callable[[RpcClient], None | collections.abc.Awaitable[None]],
        host: str | None = None,
        port: int = 3755,
        protocol: RpcProtocol = RpcProtocol.TCP,
    ):
        self.callback = callback
        self.host = host
        self.port = port
        self.protocol = protocol
        if self.host is None:
            if self.protocol == RpcProtocol.TCP:
                self.host = "localhost"
            elif self.protocol == RpcProtocol.LOCAL_SOCKET:
                self.host = "shv.sock"
            else:
                raise RuntimeError(f"Invalid protocol: {self.protocol}")

    async def run(self):
        """Run server and accept new clients."""
        if self.protocol == RpcProtocol.TCP:
            server = await asyncio.start_server(
                self._client_connect, host=self.host, port=self.port
            )
        elif self.protocol == RpcProtocol.LOCAL_SOCKET:
            server = await asyncio.start_unix_server(
                self._client_connect, path=self.host
            )
        else:
            raise RuntimeError(f"Invalid protocol: {self.protocol}")
        async with server:
            await server.serve_forever()

    async def _client_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        peername = writer.get_extra_info("peername")
        logger.info("New client connected: %s", str(peername))
        client = RpcClient(reader, writer)
        res = self.callback(client)
        if isinstance(res, collections.abc.Awaitable):
            await res
        logger.info("Client disconnected: %s", str(peername))
