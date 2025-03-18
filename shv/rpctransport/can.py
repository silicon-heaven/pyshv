"""Connection over CAN bus."""

from __future__ import annotations

import asyncio
import collections.abc
import logging
import random
import typing
import weakref

import can

from .abc import RpcClient, RpcServer

logger = logging.getLogger(__name__)


class RpcCAN:
    """The SHV RPC CAN Bus management operations."""

    socketcan_map: typing.ClassVar[weakref.WeakValueDictionary[str, RpcCAN]] = (
        weakref.WeakValueDictionary()
    )
    """Map of the socket can bus."""

    def __init__(self, bus: can.BusABC) -> None:
        self.bus = bus
        self._registered = False

    def __str__(self) -> str:
        return self.bus.channel_info

    @classmethod
    def socketcan(cls, interface: str) -> RpcCAN:
        """Get :class:`RpcCAN` for given socket CAN interface."""
        res = cls.socketcan_map.get(interface)
        if res is None:
            res = RpcCAN(can.Bus(channel=interface, interface="socketcan"))
            cls.socketcan_map[interface] = res
        return res

    def _receive(self) -> None:
        if msg := self.bus.recv(0):
            print(msg)

    def send(self, src: int, dest: int, data: bytes) -> None:
        """Send SHV RPC message in multiple CAN frames."""
        assert 0 <= dest <= 255
        count = -1
        off = 0
        datalen = len(data)
        for siz in (64, 48, 32, 24, 20, 16, 12, 8, 7, 6, 5, 4, 3, 2, 1):
            while (datalen + 1) // siz:
                datalen -= siz - 1
                self.bus.send(
                    can.Message(
                        arbitration_id=(0x80 if datalen else 0)  # NotLast
                        + (0x40 if count < 0 else 0)  # First
                        + 0x20  # QoS
                        + src,
                        is_extended_id=False,
                        data=bytes([dest if count < 0 else count])
                        + data[off : siz - 1],
                        is_fd=True,
                    )
                )
                count = (count + 1) % 0x100
                off += siz - 1

    async def listen(self, callback: collections.abc.Callable, address: int) -> None:
        pass


class RpcClientCAN(RpcClient):
    """RPC client communicating over CAN bus."""

    def __init__(
        self, location: str | RpcCAN, address: int, local_address: int | None = None
    ) -> None:
        self._location = location
        self._can: RpcCAN | None = None
        self._src: int | None = local_address
        self._dest = address
        self._recv: asyncio.Queue[bytes] = asyncio.Queue()

    def __str__(self) -> str:
        return f"can://{self._location}:{self._dest}[{self._src}]"

    async def _send(self, msg: bytes) -> None:
        if self._can is None:
            raise EOFError("Not connected")
        assert self._src is not None
        self._can.send(self._src, self._dest, msg)

    async def _receive(self) -> bytes:
        return await self._recv.get()

    async def reset(self) -> None:
        if not self.connected:
            self._can = (
                RpcCAN.socketcan(self._location)
                if isinstance(self._location, str)
                else self._location
            )
            assert self._src is not None  # TODO
            await self._can.listen(self._recv.put, self._src)
            logger.debug("%s: Connected", self)
        else:
            await super().reset()

    @property
    def connected(self) -> bool:
        return self._can is not None

    def _disconnect(self) -> None:
        pass


class RpcServerCAN(RpcServer):
    """RPC server listening on CAN bus."""

    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], collections.abc.Awaitable[None] | None
        ],
        location: str | RpcCAN,
        address: int | None = None,
    ) -> None:
        if isinstance(location, str):
            location = RpcCAN(can.Bus(channel=location, interface="socketcan"))
        self.rpccan = location
        self._address = address
        self._close = asyncio.Event()
        self._notifier: can.Notifier | None = None
        self._clients: dict[int, tuple[RpcServerCAN.Client, asyncio.Queue[bytes]]] = {}

    def __str__(self) -> str:
        return f"server.can://{self._location}:{self._address}"

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
