"""Functions providing helpers for client creation based on the RPC URL."""

import collections.abc

from ..rpcurl import RpcProtocol, RpcUrl
from .abc import RpcClient, RpcServer
from .stream import RpcProtocolSerial, RpcProtocolSerialCRC, RpcProtocolStream
from .tcp import RpcClientTCP, RpcServerTCP
from .tty import RpcClientTTY, RpcServerTTY
from .unix import RpcClientUnix, RpcServerUnix
from .ws import RpcClientWebSockets, RpcServerWebSockets, RpcServerWebSocketsUnix


def init_rpc_client(url: RpcUrl | str) -> RpcClient:
    """Initialize correct :class:`RpcClient` for given URL.

    :param url: RPC URL specifying the connection target.
    :return: Chosen :class:`RpcClient` child instance based on the passed URL.
    """
    if isinstance(url, str):
        url = RpcUrl.parse(url)
    match url.protocol:
        case RpcProtocol.TCP:
            return RpcClientTCP(url.location, url.port, RpcProtocolStream)
        case RpcProtocol.TCPS:
            return RpcClientTCP(url.location, url.port, RpcProtocolSerial)
        case RpcProtocol.UNIX:
            return RpcClientUnix(url.location, RpcProtocolStream)
        case RpcProtocol.UNIXS:
            return RpcClientUnix(url.location, RpcProtocolSerial)
        case RpcProtocol.TTY:
            return RpcClientTTY(url.location, url.baudrate, RpcProtocolSerialCRC)
        case RpcProtocol.WS:
            return RpcClientWebSockets(url.location)
        case _:
            raise NotImplementedError(f"Unimplemented protocol: {url.protocol}")


async def connect_rpc_client(url: RpcUrl | str) -> RpcClient:
    """Initialize and establish :class:`RpcClient` connection for given URL.

    Compared to the :func:`init_rpc_client` this also calls
    :meth:`RpcClient.reset` to establish the connection.

    :param url: RPC URL specifying the connection target.
    :return: Chosen :class:`RpcClient` child instance based on the passed URL.
    """
    res = init_rpc_client(url)
    await res.reset()
    return res


async def create_rpc_server(
    client_connected_cb: collections.abc.Callable[
        [RpcClient], collections.abc.Awaitable[None] | None
    ],
    url: RpcUrl | str,
) -> RpcServer:
    """Create server listening on given URL.

    :param client_connected_cb: function called for every new client connected.
    :param url: RPC URL specifying where server should listen.
    """
    res: RpcServer
    if isinstance(url, str):
        url = RpcUrl.parse(url)
    match url.protocol:
        case RpcProtocol.TCP:
            res = RpcServerTCP(
                client_connected_cb, url.location, url.port, RpcProtocolStream
            )
        case RpcProtocol.TCPS:
            res = RpcServerTCP(
                client_connected_cb, url.location, url.port, RpcProtocolSerial
            )
        case RpcProtocol.UNIX:
            res = RpcServerUnix(client_connected_cb, url.location, RpcProtocolStream)
        case RpcProtocol.UNIXS:
            res = RpcServerUnix(client_connected_cb, url.location, RpcProtocolSerial)
        case RpcProtocol.TTY:
            res = RpcServerTTY(
                client_connected_cb, url.location, url.baudrate, RpcProtocolSerialCRC
            )
        case RpcProtocol.WS:
            if url.port != -1:
                res = RpcServerWebSockets(client_connected_cb, url.location, url.port)
            else:
                res = RpcServerWebSocketsUnix(client_connected_cb, url.location)
        case _:
            raise NotImplementedError(f"Unimplemented protocol: {url.protocol}")
    await res.listen()
    return res
