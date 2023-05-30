"""Common state for the RPC broker that works as server in the SHV network."""
import asyncio
import logging

from ..rpcclient import RpcClient
from ..rpcserver import create_rpc_server
from .rpcbrokerclient import RpcBrokerClient
from .rpcbrokerconfig import RpcBrokerConfig

logger = logging.getLogger(__name__)


class RpcBroker:
    """SHV RPC broker.

    The broker manages multiple RpcClient instances and exchanges messages
    between them.
    """

    def __init__(self, config: RpcBrokerConfig) -> None:
        self.clients: dict[int, RpcBrokerClient] = {}
        self.next_caller_id = 0
        self.config = config
        self.servers: dict[str, asyncio.Server] = {}

    def add_client(self, client: RpcClient):
        """Add a new client to be handled by the broker.

        :param client: RPC client instance to be handled by broker.
        """
        # TODO try to reuse older caller IDs to send smaller messages
        cid = self.next_caller_id
        self.next_caller_id += 1
        self.clients[cid] = RpcBrokerClient(client, None, self, cid)
        logger.info("Client registered to broker with ID: %s", cid)

    def peer_on_path(self, path: str) -> tuple[RpcBrokerClient, str] | None:
        """Locate client mounted on given path.

        :return: client associated with this mount point and path relative to
            the client or None if there is no such client.
        """
        pth = path.split("/")

        if (
            len(pth) >= 4
            and pth[0] == ".broker"
            and pth[1] == "clients"
            and pth[3] == "app"
        ):
            try:
                client = self.clients[int(pth[2], 10)]
            except (ValueError, KeyError):
                return None
            return (client, "/".join(pth[4:])) if client else None

        matches = sorted(
            [
                (c, pth[len(c.mount_point) :])
                for c in self.clients.values()
                if c.mount_point and pth[: len(c.mount_point)] == c.mount_point
            ],
            key=lambda v: len(v[1]),
            reverse=True,
        )
        if len(matches) > 0:
            return matches[0][0], "/".join(matches[0][1])
        return None

    async def start_serving(self) -> None:
        """Start accepting connectons on all configured servers."""
        for name, url in self.config.listen.items():
            if name not in self.servers:
                self.servers[name] = await create_rpc_server(self.add_client, url)

    async def serve_forever(self) -> None:
        """Serve all configured servers."""
        await self.start_serving()
        await asyncio.gather(
            *(server.serve_forever() for server in self.servers.values()),
            return_exceptions=True,
        )
        # TODO handle returned errors

    def close(self) -> None:
        for server in self.servers.values():
            server.close()

    async def wait_closed(self) -> None:
        await asyncio.gather(
            *(server.wait_closed() for server in self.servers.values()),
            return_exceptions=True,
        )