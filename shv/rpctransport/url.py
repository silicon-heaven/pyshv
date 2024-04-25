"""Functions providing helpers for client creation based on the RPC URL."""

import collections.abc

from ..rpcurl import RpcProtocol, RpcUrl
from .abc import RpcClient, RpcServer
from .stream import RpcProtocolSerial, RpcProtocolSerialCRC, RpcProtocolStream
from .tcp import RpcClientTCP, RpcServerTCP
from .tty import RpcClientTTY, RpcServerTTY
from .unix import RpcClientUnix, RpcServerUnix


def init_rpc_client(url: RpcUrl) -> RpcClient:
    """Initialize correct :class:`RpcClient` for given URL.

    :param url: RPC URL specifying the connection target.
    :return: Chosen :class:`RpcClient` child instance based on the passed URL.
    """
    match url.protocol:
        case RpcProtocol.TCP:
            return RpcClientTCP(url.location, url.port, RpcProtocolStream)
        case RpcProtocol.TCPS:
            return RpcClientTCP(url.location, url.port, RpcProtocolSerial)
        case RpcProtocol.UNIX:
            return RpcClientUnix(url.location, RpcProtocolStream)
        case RpcProtocol.UNIXS:
            return RpcClientUnix(url.location, RpcProtocolSerial)
        case RpcProtocol.SERIAL:
            return RpcClientTTY(url.location, url.baudrate, RpcProtocolSerialCRC)
        case _:
            raise NotImplementedError(f"Unimplemented protocol: {url.protocol}")


async def connect_rpc_client(url: RpcUrl) -> RpcClient:
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
