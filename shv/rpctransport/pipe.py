"""Connection over Pipes or socket."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import typing

from .stream import (
    RpcClientStream,
    RpcProtocolSerial,
    RpcTransportProtocol,
)

logger = logging.getLogger(__name__)


class RpcClientPipe(RpcClientStream):
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
        loop = asyncio.get_running_loop()

        if isinstance(rpipe, int):
            rpipe = os.fdopen(rpipe, mode="r")
        reader = asyncio.StreamReader(loop=loop)
        rprotocol = asyncio.StreamReaderProtocol(reader, loop=loop)
        await loop.connect_read_pipe(lambda: rprotocol, rpipe)

        if isinstance(wpipe, int):
            wpipe = os.fdopen(wpipe, mode="w")
        if sys.version_info < (3, 12):
            wprotocol = rprotocol
        else:
            wprotocol = asyncio.StreamReaderProtocol(None, loop=loop)
        wtransport, _ = await loop.connect_write_pipe(lambda: wprotocol, wpipe)
        writer = asyncio.StreamWriter(wtransport, wprotocol, None, loop)

        return cls(reader, writer, protocol)

    @classmethod
    async def open_pair(
        cls,
        protocol: type[RpcTransportProtocol] = RpcProtocolSerial,
        flags: int = 0,
    ) -> tuple[RpcClientPipe, RpcClientPipe]:
        """Create pair of clients that are interconnected over the pipe.

        :param protocol: The protocol factory to be used.
        :param flags: Flags passed to :func:`os.pipe2`.
        :return: Pair of clients that are interconnected over Unix pipes.
        """
        pr1, pw1 = os.pipe2(flags)
        pr2, pw2 = os.pipe2(flags)
        client1 = await cls.fdopen(pr1, pw2, protocol)
        client2 = await cls.fdopen(pr2, pw1, protocol)
        return client1, client2
