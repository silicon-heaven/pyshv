"""Connection over CAN bus."""

from __future__ import annotations

import asyncio
import logging
import random

import can

from .abc import RpcClient, RpcServer

logger = logging.getLogger(__name__)


class RpcServerCAN(RpcServer):
    """RPC server listening on CAN bus."""

    def __init__(self, bus: can.Bus, address: int | None = None) -> None:
        self.bus = bus
        self._address = address
        self._close = asyncio.Event()
        self._notifier: can.Notifier | None = None
        self._clients: dict[int, tuple[RpcServerCAN.Client, asyncio.Queue[bytes]]] = {}

    @property
    def address(self) -> int | None:
        """The CAN address assigned to this server."""
        return self._address

    async def _message(self, msg: can.Message) -> None:
        """Handle received CAN message."""
        print(msg)  # TODO debug

    def is_serving(self) -> bool:  # noqa: D102
        return not self._close.is_set() and self._notifier is not None

    async def listen(self) -> None:  # noqa: D102
        if self._notifier is not None:
            return
        self._notifier = can.Notifier(self.bus)
        if self._address is None:
            reader = can.AsyncBufferedReader()
            self._notifier.add_listener(reader)
            while True:
                self._address = random.randint(126, 255)  # noqa: S311
                for _ in range(5):
                    self.bus.send(
                        can.Message(
                            is_fd=True, is_remote_fram=True, dlc=0xF, check=True
                        )
                    )
                    # TODO check if someone complains
                break
            # TODO check if address is not used
            self._notifier.remove_listener(reader)
        self._notifier.add_listener(self._message)

    async def listen_forewer(self) -> None:  # noqa: D102
        await self.listen()
        await self.wait_terminated()

    def close(self) -> None:  # noqa: D102
        self._close.set()

    async def wait_closed(self) -> None:  # noqa: D102
        await self._close.wait()

    def terminate(self) -> None:  # noqa: D102
        self.close()
        for client in self._clients.values():
            client[0].disconnect()

    async def wait_terminated(self) -> None:  # noqa: D102
        await self.wait_closed()
        res = await asyncio.gather(
            *(c[0].wait_disconnect() for c in self._clients.values()),
            return_exceptions=True,
        )
        excs = [v for v in res if isinstance(v, BaseException)]
        if excs:
            if len(excs) == 1:
                raise excs[0]
            raise BaseExceptionGroup("", excs)

    def discover(self) -> list[int]:
        """Discover the addresses of active devices on the CAN Bus."""
        raise NotImplementedError

    @classmethod
    def socketcan(cls, interface: str, address: int | None = None) -> RpcServerCAN:
        """Create new CAN Bus RPC server on SocketCAN."""
        raise NotImplementedError

    class Client(RpcClient):
        """RPC connection to SHV peer over CAN bus."""

        def __init__(self, server: RpcServerCAN, address: int) -> None:
            self._server = server
            self._address = address
            self._disconnected = asyncio.Event()

        def __str__(self) -> str:
            return f"can:INTERFACE:{self._server._address}:{self._address}"

        async def _send(self, msg: bytes) -> None:
            # TODO
            raise NotImplementedError

        async def _receive(self) -> bytes:
            return await self._server._clients[self._address][1].get()

        @property
        def connected(self) -> bool:  # noqa: D102
            return not self._disconnected.is_set()

        def _disconnect(self) -> None:
            del self._server._clients[self._address]
            self._disconnected.set()

        async def wait_disconnect(self) -> None:
            """Wait for the client's disconnection."""
            await self._disconnected.wait()
