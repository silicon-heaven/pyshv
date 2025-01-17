"""Connection over TCP/IP."""

from __future__ import annotations

import asyncio
import collections.abc
import logging
import ssl

from .abc import RpcClient
from .stream import (
    RpcClientStream,
    RpcProtocolBlock,
    RpcProtocolSerial,
    RpcServerStream,
    RpcTransportProtocol,
)

logger = logging.getLogger(__name__)


class RpcClientTCP(RpcClientStream):
    """RPC connection to some SHV peer over TCP/IP."""

    def __init__(
        self,
        location: str = "localhost",
        port: int = 3755,
        protocol: type[RpcTransportProtocol] = RpcProtocolBlock,
        ssl: ssl.SSLContext | None = None,
    ) -> None:
        super().__init__(protocol)
        self.location = location
        self.port = port
        self.ssl = ssl

    def __str__(self) -> str:
        proto = "tcp" if self.ssl is None else "ssl"
        if self.protocol is RpcProtocolSerial:
            proto += "s"
        location = f"[{self.location}]" if ":" in self.location else self.location
        return f"{proto}:{location}:{self.port}"

    async def _open_connection(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        return await asyncio.open_connection(self.location, self.port, ssl=self.ssl)

    @property
    def secure(self) -> bool:  # noqa: D102
        return self.ssl is not None


class RpcServerTCP(RpcServerStream):
    """RPC server listenting for SHV connections in TCP/IP."""

    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], collections.abc.Awaitable[None] | None
        ],
        location: str | None = None,
        port: int = 3755,
        protocol: type[RpcTransportProtocol] = RpcProtocolBlock,
        ssl: ssl.SSLContext | None = None,
    ) -> None:
        super().__init__(client_connected_cb, protocol)
        self.location = location
        self.port = port
        self.ssl = ssl

    def __str__(self) -> str:
        proto = "tcp" if self.ssl is None else "ssl"
        if self.protocol is RpcProtocolSerial:
            proto += "s"
        location = (
            "locahost"
            if self.location is None
            else f"[{self.location}]"
            if ":" in self.location
            else self.location
        )
        return f"server.{proto}:{location}:{self.port}"

    async def _create_server(self) -> asyncio.Server:
        # Note: The hack for '::' here is to allow really bind to all
        # interfaces as that is what this should do and not just loopback.
        return await asyncio.start_server(
            self._client_connect,
            host=None if self.location == "::" else self.location,
            port=self.port,
            ssl=self.ssl,
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

    class Client(RpcServerStream.Client):
        """RPC client for TCP server connection."""

        def __str__(self) -> str:
            assert isinstance(self._server, RpcServerTCP)
            proto = "tcp" if self._server.ssl is None else "ssl"
            if self.protocol is RpcProtocolSerial:
                proto += "s"
            peername = self._writer.get_extra_info("peername")
            location = f"[{peername[0]}]" if ":" in peername[0] else peername[0]
            return f"tcp:{location}:{peername[1]}"

        @property
        def secure(self) -> bool:  # noqa: D102
            assert isinstance(self._server, RpcServerTCP)
            return self._server.ssl is not None
