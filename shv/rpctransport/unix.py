"""Connection over Unix domain named socket."""

import asyncio
import collections.abc
import logging

from .abc import RpcClient
from .stream import (
    RpcClientStream,
    RpcProtocolSerial,
    RpcServerStream,
    RpcTransportProtocol,
)

logger = logging.getLogger(__name__)


class RpcClientUnix(RpcClientStream):
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


class RpcServerUnix(RpcServerStream):
    """RPC server listenting for SHV connections on Unix domain named socket."""

    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], collections.abc.Awaitable[None] | None
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

    class Client(RpcServerStream.Client):
        """RPC client for Unix server connection."""

        def __str__(self) -> str:
            return f"unix:{self._writer.get_extra_info('peername')}"
