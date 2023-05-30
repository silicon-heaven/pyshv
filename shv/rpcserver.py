"""RPC server that waits for clients connection."""
import asyncio
import collections.abc
import logging
import typing

from .rpcclient import RpcClient
from .rpcurl import RpcProtocol, RpcUrl

logger = logging.getLogger(__name__)


async def create_rpc_server(
    client_connected_cb: typing.Callable[
        [RpcClient], None | collections.abc.Awaitable[None]
    ],
    url: RpcUrl,
) -> asyncio.Server:
    """Create server listening on given URL."""

    async def client_connect(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        client = RpcClient(reader, writer)
        res = client_connected_cb(client)
        if isinstance(res, collections.abc.Awaitable):
            await res

    if url.protocol is RpcProtocol.TCP:
        server = await asyncio.start_server(
            client_connect, host=url.host, port=url.port
        )
    elif url.protocol is RpcProtocol.LOCAL_SOCKET:
        server = await asyncio.start_unix_server(client_connect, path=url.host)
    else:
        raise RuntimeError(f"Invalid protocol: {url.protocol}")
    return server
