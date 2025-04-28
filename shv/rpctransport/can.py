"""Connection over CAN bus."""

from __future__ import annotations

import asyncio
import collections
import collections.abc
import concurrent
import dataclasses
import enum
import logging
import weakref

import can
import can.interfaces.socketcan

from .abc import RpcClient, RpcServer

logger = logging.getLogger(__name__)


class RpcCAN:
    """The SHV RPC CAN Bus management operations."""

    class Connection:
        """Single connection between server and client."""

        def __init__(self, rpccan: RpcCAN, local: int, remote: int) -> None:
            self._rpccan = rpccan
            self._local = local
            self._remote = remote
            # TODO asyncio.Queue would be better but it can't be terminated in
            # this version of Python and thus we can't wake blocked receive
            # calls.
            self._received: collections.deque[bytes] = collections.deque()
            self._receive_event = asyncio.Event()
            self._connected = True
            self._disconnect_event = asyncio.Event()
            self._disconnect_task: asyncio.Task | None = None

        @property
        def rpccan(self) -> RpcCAN:
            """Access to the associated :class:`RpcCAN`."""
            return self._rpccan

        @property
        def local_address(self) -> int:
            """The local address of the connection."""
            return self._local

        @property
        def remote_address(self) -> int:
            """The remote address of the connection."""
            return self._remote

        @property
        def connected(self) -> bool:
            """Identify if connection is still declared to be connected."""
            return self._connected

        async def send(self, msg: bytes) -> None:
            """Send message in this connection."""
            # Yield to loop to ensure that we receive messages before sending
            await asyncio.sleep(0.001)
            if not self._connected:
                raise EOFError("Not connected")
            await self._rpccan._send(self._local, self._remote, msg)

        async def receive(self) -> bytes:
            """Receive message from this connection."""
            await self._receive_event.wait()
            if not self._received and not self._connected:
                raise EOFError("Not connected")
            res = self._received.popleft()
            if not self._received and self._connected:
                self._receive_event.clear()
            return res

        def disconnect(self, remote: bool) -> None:
            """Disconnect this connection."""
            if (
                self._remote in self._rpccan._peers
                and self._local in self._rpccan._peers[self._remote].connections
            ):
                del self._rpccan._peers[self._remote].connections[self._local]
                if not self._rpccan._peers[self._remote].connections:
                    del self._rpccan._peers[self._remote]
                self._connected = False
                self._receive_event.set()
                if not remote:
                    self._disconnect_task = asyncio.create_task(
                        self._rpccan._send(self._local, self._remote, b"")
                    )
                self._disconnect_event.set()
                self._rpccan._possibly_unregister()

        async def wait_disconnect(self) -> None:
            """Wait for the disconnect."""
            await self._disconnect_event.wait()
            if self._disconnect_task is not None:
                await self._disconnect_task

    class RTR(enum.IntEnum):
        """Data lenght for the RTR CAN frames used by the protocol."""

        MSGABORT = 0
        """Abort partially sent out message."""
        ANNOUNCE = 5
        """Anounce server."""
        DISCOVER = 6
        """Requests servers to send announce."""
        # TODO we are missing the way to autonegotiate the client address

    @dataclasses.dataclass
    class _Peer:
        data: bytearray = dataclasses.field(default_factory=bytearray)
        counter: int = -1
        dest: int = -1

        connections: dict[int, RpcCAN.Connection] = dataclasses.field(
            default_factory=dict
        )

        def clear(self) -> None:
            """Clear the received message."""
            self.data.clear()
            self.counter = -1
            self.dest = -1

    def __init__(self, bus: can.BusABC) -> None:
        self.bus = bus
        self._notifier: can.Notifier | None = None
        self._sendexecutor = concurrent.futures.ThreadPoolExecutor(1)
        self._peers: dict[int, RpcCAN._Peer] = {}
        self._binds: dict[
            int,
            collections.abc.Callable[
                [RpcCAN.Connection], collections.abc.Awaitable[None]
            ],
        ] = {}
        self._announcers: set[
            collections.abc.Callable[[int], collections.abc.Awaitable[None] | None]
        ] = set()

    @classmethod
    def socketcan(cls, interface: str) -> RpcCAN:
        """Get :class:`RpcCAN` for given socket CAN interface."""
        return cls(
            can.Bus(
                channel=interface, interface="socketcan", fd=True, local_loopback=False
            )
        )

    @classmethod
    def virtualcan(cls, name: str) -> RpcCAN:
        """Get :class:`RpcCAN` for given virtual interface name.

        This virtual interface should be used primarilly for the testing of the
        CAN functionality. It works only in single process.
        """
        return cls(can.Bus(name, interface="virtual", protocol=can.CanProtocol.CAN_FD))

    def __str__(self) -> str:
        if isinstance(self.bus, can.interfaces.socketcan.SocketcanBus):
            return self.bus.channel
        else:
            return self.bus.channel_info

    async def _receive(self, msg: can.Message) -> None:
        if msg.is_error_frame or msg.is_extended_id:
            return  # TODO what to do with error or extended id frames?

        aid = msg.arbitration_id
        src = aid & 0xFF
        peer = self._peers.get(src)
        if msg.is_remote_frame:
            match msg.dlc:
                case self.RTR.MSGABORT:
                    if peer is not None:
                        peer.clear()
                case self.RTR.ANNOUNCE:
                    for cb in self._announcers:
                        callres = cb(src)
                        if isinstance(callres, collections.abc.Awaitable):
                            await callres
                case self.RTR.DISCOVER:
                    for address in self._binds:
                        await self._send_rtr(address, self.RTR.ANNOUNCE)
            return

        # Data frame
        first = aid & 1 << 9
        last = not aid & 1 << 10
        if len(msg.data) < (2 if first else 1):
            return  # Message with not enough bytes are invalid
        counter = msg.data[0]
        if last and counter >> 4:
            msg.data = msg.data[: -(counter >> 4)]  # Remove stuffed bytes
        if first:
            dest = msg.data[1]
            if msg.data[2:] == b"":  # Disconnect
                if peer is not None and dest in peer.connections:
                    peer.connections[dest].disconnect(True)
                return
            if peer is None or dest not in peer.connections:
                if (callback := self._binds.get(dest)) is not None:
                    if peer is None:
                        peer = self._peers[src] = self._Peer()
                    con = self.Connection(self, dest, src)
                    peer.connections[dest] = con
                    callres = callback(con)
                    if isinstance(callres, collections.abc.Awaitable):
                        await callres
                    if msg.data[2:] == b"\0":
                        return  # Do not propagate initial reset
                else:
                    return  # Message is not for us
            peer.clear()
            peer.dest = dest
            peer.counter = 0
        elif peer is None or peer.dest == -1:
            return  # Not for us or we missed the first frame thus ignore
        if (counter ^ peer.counter) & (0xF if last else 0xFF) != 0:
            # Invalid counter signals missed frames
            peer.clear()
            return
        peer.counter = (peer.counter + 1) % 0x100
        peer.data.extend(msg.data[2 if first else 1 :])
        if last:
            peer.connections[peer.dest]._received.append(bytes(peer.data))
            peer.connections[peer.dest]._receive_event.set()
            peer.clear()

    async def _send(self, src: int, dest: int, data: bytes) -> None:
        """Send SHV RPC message in multiple CAN frames."""
        if 0 > src > 255:
            raise ValueError(f"Invalid source address: {src}")
        if 0 > dest > 255:
            raise ValueError(f"Invalid destination address: {dest}")
        first = True
        count = 0
        off = 0
        datalen = len(data)
        qos = datalen > 512
        sizes = (1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64)
        while True:
            overhead = 2 if first else 1
            dlen = min(datalen, 64 - overhead)
            last = dlen == datalen
            stuffing = (
                next(v for v in sizes if (dlen + overhead) <= v) - dlen - overhead
            )
            aid = (1 << 10) if not last else 0  # notLastFrame
            aid += 1 << 9 if first else 0  # firstFrame
            aid += 1 << 8 if qos else 0  # QoS
            aid += src
            msgdata = (
                bytes([(count & 0xF) + (stuffing << 4) if last else count])
                + (bytes([dest]) if first else b"")
                + data[off : off + dlen]
                + (b"\0" * stuffing)
            )
            await asyncio.get_running_loop().run_in_executor(
                self._sendexecutor,
                self.bus.send,
                can.Message(
                    arbitration_id=aid, data=msgdata, is_extended_id=False, is_fd=True
                ),
            )
            off += dlen
            datalen -= dlen
            count = (count + 1) % 0x100
            first = False
            if last:
                break

    async def _send_rtr(self, src: int, dlc: int) -> None:
        """Send CAN RTR message as compatible with SHV RPC."""
        await asyncio.get_running_loop().run_in_executor(
            self._sendexecutor,
            self.bus.send,
            can.Message(
                arbitration_id=0x10 + src,  # firstFrame and not notLastFrame
                dlc=dlc,
                is_extended_id=False,
                is_fd=True,
            ),
        )

    async def _ensure_registration(self) -> None:
        if self._notifier is None:
            self._notifier = can.Notifier(
                self.bus,
                (self._receive,),
                timeout=0.05,
                loop=asyncio.get_running_loop(),
            )

    def _possibly_unregister(self) -> None:
        if self._notifier is not None and not self._peers and not self._binds:
            self._notifier.stop()
            self._notifier = None

    async def connect(self, local: int | None, remote: int) -> Connection:
        """Create client connection between given local and remote address."""
        if not 0 < remote < 128:
            raise ValueError(f"Invalid remote address: {remote}")
        if local is None:
            local = 150  # TODO we need to select address dynamically
        elif not 128 < local < 192:
            raise ValueError(f"Invalid local address: {local}")
        if remote not in self._peers:
            self._peers[remote] = self._Peer()
        if local in self._peers[remote].connections:
            raise ValueError(f"Connection between {local}:{remote} already registered")
        await self._ensure_registration()
        self._peers[remote].connections[local] = self.Connection(self, local, remote)
        return self._peers[remote].connections[local]

    async def bind(
        self,
        local: int,
        callback: collections.abc.Callable[
            [Connection], collections.abc.Awaitable[None]
        ],
    ) -> None:
        """Start listening for the CAN connections."""
        if not 0 < local < 128:
            raise ValueError(f"Invalid address: {local}")
        if local in self._binds:
            raise ValueError(f"Address {local} is already bound")
        await self._ensure_registration()
        self._binds[local] = callback
        await self._send_rtr(local, self.RTR.ANNOUNCE)

    def isbound(self, local: int) -> bool:
        """Check if given address is bound or not."""
        return local in self._binds

    def unbind(self, local: int) -> None:
        """Stop listening for the CAN connections."""
        del self._binds[local]
        self._possibly_unregister()

    async def expect_announce(
        self,
        callback: collections.abc.Callable[
            [int], collections.abc.Awaitable[None] | None
        ],
    ) -> None:
        """Add callback for servers announcements."""
        self._announcers.add(callback)
        await self._ensure_registration()

    def unexpect_announce(
        self,
        callback: collections.abc.Callable[
            [int], collections.abc.Awaitable[None] | None
        ],
    ) -> None:
        """Remove callback for server announcements."""
        self._announcers.remove(callback)
        self._possibly_unregister()

    async def discover(self) -> None:
        """Send discovery request so all present servers emit announcement."""
        await self._send_rtr(0xFF, self.RTR.DISCOVER)


class RpcClientCAN(RpcClient):
    """RPC client communicating over CAN bus."""

    def __init__(
        self, location: str | RpcCAN, address: int, client_address: int | None = None
    ) -> None:
        if not 0 < address < 128:
            raise ValueError(f"Invalid address: {address}")
        if client_address is not None and not 0 < client_address < 128:
            raise ValueError(f"Invalid client address: {client_address}")
        super().__init__()
        self._rpccan: RpcCAN = (
            location if isinstance(location, RpcCAN) else RpcCAN.socketcan(location)
        )
        self._address = address
        self._client_address = client_address
        self._con: RpcCAN.Connection | None = None

    @property
    def rpccan(self) -> RpcCAN:
        """Access to the associated :class:`RpcCAN`."""
        return self._rpccan

    def __str__(self) -> str:
        return f"can://{self._rpccan}:{self._address}[{self._client_address}]"

    async def _send(self, msg: bytes) -> None:
        if self._con is None:
            raise EOFError("Not connected")
        await self._con.send(msg)

    async def _receive(self) -> bytes:
        if self._con is None:
            raise EOFError("Not connected")
        return await self._con.receive()

    async def reset(self) -> None:  # noqa: D102
        if not self.connected:
            self._con = await self.rpccan.connect(self._client_address, self._address)
            logger.debug("%s: Connected", self)
        # Always send reset message
        await super().reset()

    @property
    def connected(self) -> bool:  # noqa: D102
        return self._con is not None and self._con.connected

    def _disconnect(self) -> None:
        if self._con is not None:
            self._con.disconnect(False)

    async def wait_disconnect(self) -> None:  # noqa D027
        if self._con is not None:
            await self._con.wait_disconnect()


class RpcServerCAN(RpcServer):
    """RPC server listening on CAN bus."""

    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], collections.abc.Awaitable[None] | None
        ],
        location: str | RpcCAN,
        address: int,
    ) -> None:
        if not 0 < address < 128:
            raise ValueError(f"Invalid address: {address}")
        self.client_connected_cb = client_connected_cb
        """Callbact that is called when new client is connected."""
        self._rpccan: RpcCAN = (
            location if isinstance(location, RpcCAN) else RpcCAN.socketcan(location)
        )
        """Associated instance of :class:`RpcCAN`."""
        self._address = address
        self._clients: weakref.WeakSet[RpcServerCAN.Client] = weakref.WeakSet()

    @property
    def rpccan(self) -> RpcCAN:
        """Access to the associated :class:`RpcCAN`."""
        return self._rpccan

    def __str__(self) -> str:
        return f"server.can://{self.rpccan}:{self._address}"

    @property
    def address(self) -> int | None:
        """The CAN address assigned to this server."""
        return self._address

    def is_serving(self) -> bool:  # noqa: D102
        return self._rpccan.isbound(self._address)

    async def listen(self) -> None:  # noqa: D102
        if not self.is_serving():
            await self.rpccan.bind(self._address, self._client_connect)
            logger.debug("%s: Listening", self)

    async def listen_forewer(self) -> None:  # noqa: D102
        await self.listen()
        await self.wait_terminated()

    async def _client_connect(self, connection: RpcCAN.Connection) -> None:
        client = self.Client(connection, self)
        self._clients.add(client)
        res = self.client_connected_cb(client)
        if isinstance(res, collections.abc.Awaitable):
            await res

    def close(self) -> None:  # noqa: D102
        if self.is_serving():
            self.rpccan.unbind(self._address)
            self._queue = None
            logger.debug("%s: No longer listening", self)

    async def wait_closed(self) -> None:  # noqa: D102
        pass  # Unbind is enough. Nothing to wait for.

    def terminate(self) -> None:  # noqa: D102
        self.close()
        for client in self._clients:
            client.disconnect()

    async def wait_terminated(self) -> None:  # noqa: D102
        res = await asyncio.gather(
            *(c.wait_disconnect() for c in self._clients),
            return_exceptions=True,
        )
        excs = [v for v in res if isinstance(v, BaseException)]
        if excs:
            if len(excs) == 1:
                raise excs[0]
            raise BaseExceptionGroup("", excs)

    class Client(RpcClient):
        """RPC connection to SHV server peer over CAN bus."""

        def __init__(self, connection: RpcCAN.Connection, server: RpcServerCAN) -> None:
            super().__init__()
            self._con: RpcCAN.Connection = connection
            self._server = server

        @property
        def server(self) -> RpcServerCAN:
            """Access to the associated server."""
            return self._server

        def __str__(self) -> str:
            return f"can://{self._server.rpccan}:{self._con.remote_address}[{self._con.local_address}]"

        async def _send(self, msg: bytes) -> None:
            await self._con.send(msg)

        async def _receive(self) -> bytes:
            return await self._con.receive()

        @property
        def connected(self) -> bool:  # noqa: D102
            return self._con.connected

        def _disconnect(self) -> None:
            self._con.disconnect(False)

        async def wait_disconnect(self) -> None:  # noqa D027
            await self._con.wait_disconnect()
