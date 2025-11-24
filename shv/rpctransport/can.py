"""Connection over CAN bus."""

from __future__ import annotations

import asyncio
import collections.abc
import concurrent
import dataclasses
import enum
import errno
import logging
import random
import time
import typing
import weakref

from .__canlog import patchlogger as __patchlogger
from .abc import RpcClient, RpcServer

logger = logging.getLogger(__name__)

try:
    import can
    import can.interfaces.socketcan

    CAN_IMPORT = None
    __patchlogger(logging.getLogger("can"))
    __patchlogger(logging.getLogger("can.interfaces.socketcan.socketcan"))
    __patchlogger(logging.getLogger("can.interfaces.socketcan.socketcan.tx"))
    __patchlogger(logging.getLogger("can.interfaces.socketcan.socketcan.rx"))
except ImportError as exc:
    CAN_IMPORT = exc


class SHVCAN:
    """The interface used to manage SHV CAN-FD communication."""

    CANID_SHVCAN: typing.Final = 0x400
    CANID_UNUSED: typing.Final = 0x200
    CANID_FIRST_MASK: typing.Final = 0x100
    CANID_ADDRESS_MASK: typing.Final = 0x0FF

    class DLC(enum.IntEnum):
        """DLC used in RTR frames."""

        ADDR_ACQ = 0
        """Address acquistion."""
        ADDR_ANC_LISTEN = 1
        """Address announce for peers accepting connections."""
        ADDR_ANC_IGN = 2
        """Address announce for peers not accepting new connections."""
        ADDR_DISC_LISTEN = 5
        """Address discovery for peers accepting connections."""
        ADDR_DISC_IGN = 6
        """Address discovery for peers not accepting new connections."""
        ADDR_DISC = 7
        """Address discovery for all peers."""

    class AddressAcquisitionError(RuntimeError):
        """Failure to acquire dynamic address."""

        def __init__(self, acq_conflict: bool) -> None:
            super().__init__(
                "Dynamic address acquisition collide with other one"
                if acq_conflict
                else "Dynamic address already taken, can't acquire",
                acq_conflict,
            )

        @property
        def acq_conflict(self) -> bool:
            """Check if this is acquisition or existing assignment conflict."""
            return bool(self.args[1])

    @dataclasses.dataclass
    class Local:
        """Local address."""

        shvcan: SHVCAN
        address: int

        _peers: weakref.WeakValueDictionary[int, SHVCAN.Peer] = dataclasses.field(
            default_factory=weakref.WeakValueDictionary
        )

        def __post_init__(self) -> None:
            if self.address in self.shvcan._locals:
                raise ValueError(f"Local SHVCAN address {self.address} already used")
            self.shvcan._locals[self.address] = self
            self._new_peer_callback: (
                collections.abc.Callable[
                    [SHVCAN.Peer], collections.abc.Awaitable[None] | None
                ]
                | None
            ) = None
            self._dynfuture: asyncio.Future[bool] | None = (
                asyncio.get_running_loop().create_future()
                if 0x80 <= self.address <= 0xFF
                else None
            )

        @property
        def active(self) -> bool:
            """Check if this peer is still tied to :class:`SHVCAN`."""
            return self.shvcan._locals.get(self.address) is self

        async def announce(self) -> None:
            """Send announce."""
            await self.shvcan._send_frames((
                self._rtrframe(
                    SHVCAN.DLC.ADDR_ANC_LISTEN
                    if self.listening
                    else SHVCAN.DLC.ADDR_ANC_IGN
                ),
            ))

        async def discover(
            self, listening: bool = True, notlistening: bool = True
        ) -> None:
            """Request discovery of the active addresses on the CAN Bus."""
            dlc = {
                (True, False): SHVCAN.DLC.ADDR_DISC_LISTEN,
                (False, True): SHVCAN.DLC.ADDR_DISC_IGN,
                (True, True): SHVCAN.DLC.ADDR_DISC,
            }.get((listening, notlistening), None)
            if dlc is not None:
                await self.shvcan._send_frames((self._rtrframe(dlc),))

        @property
        def address_acquired(self) -> bool:
            """Check if address this local has is acquired by us."""
            return self._dynfuture is None

        async def dynamic_address_acquire(self) -> None:
            """Perform dynamic address acquistion.

            This has to be called at the start for addresses in dynamic address
            range.

            :raise SHVCAN.AddressAcquisitionError: In case address can't be
              acquired.
            """
            if self.active and self._dynfuture is not None:
                for _ in range(8):
                    await self.shvcan._send_frames((
                        self._rtrframe(SHVCAN.DLC.ADDR_ACQ),
                    ))
                    if (await asyncio.wait((self._dynfuture,), timeout=0.05))[0]:
                        assert self._dynfuture.done()
                        del self.shvcan._locals[self.address]
                        raise SHVCAN.AddressAcquisitionError(self._dynfuture.result())
                self._dynfuture = None

        @property
        def listening(self) -> bool:
            """If new connections are being accepted."""
            return self.active and self._new_peer_callback is not None

        async def bind(
            self,
            callback: collections.abc.Callable[
                [SHVCAN.Peer], collections.abc.Awaitable[None] | None
            ],
        ) -> None:
            """Accept new connections."""
            if self._new_peer_callback is not None:
                raise ValueError("Address already bound.")
            if self._dynfuture is not None:
                raise ValueError("Address not yet negotiated")
            self._new_peer_callback = callback
            await self.announce()

        def unbind(self) -> None:
            """Stop listening for new connections."""
            self._new_peer_callback = None

        async def deactivate(self) -> None:
            """Close the local address.

            This won't disconnect any existing connections. You must do that
            on your own.
            """
            if self.active:
                if self._peers:
                    raise RuntimeError("There are still existing connections.")
                del self.shvcan._locals[self.address]
                if self._new_peer_callback is None and not self.shvcan._locals:
                    await self.shvcan.terminate()

        def _rtrframe(self, dlc: int) -> can.Message:
            priority = dlc not in {SHVCAN.DLC.ADDR_ACQ}
            return self._frame(priority, is_remote_frame=True, dlc=dlc)

        def _frame(self, priority: bool, **kwargs: typing.Any) -> can.Message:  # noqa: ANN401
            return can.Message(
                arbitration_id=SHVCAN.CANID_SHVCAN
                + SHVCAN.CANID_UNUSED
                + (0 if priority else SHVCAN.CANID_FIRST_MASK)
                + self.address,
                is_extended_id=False,
                **kwargs,
            )

    @dataclasses.dataclass
    class Peer:
        """Peer representing handle in SHVCAN."""

        local: SHVCAN.Local
        address: int
        queue: asyncio.Queue[bytes | None] = dataclasses.field(
            default_factory=asyncio.Queue
        )

        _sendlock: asyncio.Lock = dataclasses.field(default_factory=asyncio.Lock)
        _scounter: int = dataclasses.field(
            default_factory=lambda: random.randrange(0x7F)  # noqa: S311
        )

        _rdata: bytearray = dataclasses.field(default_factory=bytearray)
        _rcounter: int = 0

        def __post_init__(self) -> None:
            if self.address in self.local._peers:
                raise ValueError(
                    f"Connection between {self.local.address} and {self.address} already used"
                )
            self._acknowledgement: asyncio.Future[None] | None = None
            self.local._peers[self.address] = self

        @property
        def connected(self) -> bool:
            """Check if this peer is still tied to :class:`SHVCAN`."""
            return self.local._peers.get(self.address) is self

        async def send(self, msg: bytes) -> None:
            """Send given message to this peer."""
            msglen = len(msg)
            if msglen == 0:
                raise ValueError("Message can't have zero length")
            first_block = msg[0:62]
            async with self._sendlock:
                frame = self._dataframe(first_block, first=True, last=msglen <= 62)
                future = asyncio.get_running_loop().create_future()
                self._acknowledgement = future
                try:
                    for _ in range(25):
                        await self.local.shvcan._send_frames((frame,))
                        if (await asyncio.wait((future,), timeout=0.2))[0]:
                            break
                    else:
                        raise EOFError("No acknowledgement in time")
                finally:
                    self._acknowledgement = None

            await self.local.shvcan._send_frames(
                self._dataframe(msg[i : i + 62], last=(i + 62) > msglen)
                for i in range(62, msglen, 62)
            )

        async def disconnect(self) -> None:
            """Close the connection to the peer."""
            if self.connected:
                del self.local._peers[self.address]
                await self.local.shvcan._send_frames((self._disconnectframe(),))
                if self.local._new_peer_callback is None and not self.local._peers:
                    await self.local.deactivate()

        def _dataframe(
            self, data: bytes, first: bool = False, last: bool = False
        ) -> can.Message:
            assert 0 < len(data) <= 62
            self._scounter = (self._scounter + 1) % 0x80
            self._scounter += 0x80 if last else 0
            return self.local._frame(
                not first, is_fd=True, data=bytes((self.address, self._scounter)) + data
            )

        def _acknowledgementframe(self) -> can.Message:
            return self.local._frame(
                True, is_fd=True, data=bytes((self.address, self._rcounter))
            )

        def _disconnectframe(self) -> can.Message:
            return self.local._frame(False, is_fd=True, data=bytes((self.address,)))

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:  # noqa: ANN401
        if CAN_IMPORT is not None:
            raise CAN_IMPORT
        self._args = args
        self._kwargs = kwargs
        self._locals: weakref.WeakValueDictionary[int, SHVCAN.Local]
        self._locals = weakref.WeakValueDictionary()
        self.bus = can.Bus(*self._args, **self._kwargs)
        if self.bus.protocol is not can.CanProtocol.CAN_FD:
            self.bus.shutdown()
            raise ValueError("Only CAN-FD is supported")
        self._notifier = can.Notifier(
            self.bus,
            (self._receive_frame,),
            timeout=0.05,
            loop=asyncio.get_running_loop(),
        )
        self._sendexecutor = concurrent.futures.ThreadPoolExecutor(1)
        self._discovery_cbs: set[collections.abc.Callable[[int, bool], None]] = set()

    def __str__(self) -> str:
        if isinstance(self.bus, can.interfaces.socketcan.SocketcanBus):
            return self.bus.channel
        else:
            return self.bus.channel_info

    def existing_local(self, address: int) -> SHVCAN.Local:
        """Get existing :class:`SHVCAN.Local` for given address."""
        return self._locals[address]

    def static_local(self, address: int) -> SHVCAN.Local:
        """Create new static local address.

        :param address: Static local address.
        :raise ValueError: In case address is not in correct range for static
          address or if address is already in use.
        """
        if not 0x00 <= address <= 0x7F:
            raise ValueError("Address must be in range from 0x0 to 0x7F")
        return self.Local(self, address)

    async def dynamic_local(self) -> SHVCAN.Local:
        """Negotiate a dynamic local address to be used.

        :return: New dynamic local address object.
        :raise RuntimeError: If there is no free dynamic address available.
        """
        # TODO possibly also exclude those we are already communicating with
        available = [v for v in range(0x80, 0x100) if v not in self._locals]
        while available:
            local = self.Local(self, random.choice(available))  # noqa: S311
            try:
                await local.dynamic_address_acquire()
            except self.AddressAcquisitionError as exc:
                if not exc.acq_conflict:
                    available.remove(local.address)
            else:
                return local
        raise RuntimeError("No free dynamic address is available")

    def register_discovery_callback(
        self, cb: collections.abc.Callable[[int, bool], None]
    ) -> None:
        """Register given callback to be called when address is announced."""
        self._discovery_cbs.add(cb)

    def unregister_discovery_callback(
        self, cb: collections.abc.Callable[[int, bool], None]
    ) -> None:
        """Remove previous added discovery callback with :meth:`register_discovery_callback`."""
        self._discovery_cbs.remove(cb)

    async def terminate(self) -> None:
        """Terminate the CAN instance."""
        if self._locals:
            raise RuntimeError("There are still existing locals.")
        self._notifier.stop()
        self.bus.shutdown()

    async def _receive_frame(self, msg: can.Message) -> None:
        if (
            msg.is_error_frame  # TODO should we not ignore error frames?
            or msg.is_extended_id
            or not bool(msg.arbitration_id & self.CANID_SHVCAN)
        ):  # Ignore extended ID frames and those with ID not for SHV CANFD
            return
        src = msg.arbitration_id & self.CANID_ADDRESS_MASK
        first = bool(msg.arbitration_id & self.CANID_FIRST_MASK)
        if msg.is_remote_frame:
            match msg.dlc:
                case SHVCAN.DLC.ADDR_ACQ:
                    if (local := self._locals.get(src, None)) is not None:
                        if local._dynfuture is not None and not local._dynfuture.done():
                            local._dynfuture.set_result(True)
                        else:
                            await local.announce()
                case SHVCAN.DLC.ADDR_ANC_LISTEN | SHVCAN.DLC.ADDR_ANC_IGN:
                    if (local := self._locals.get(src, None)) is not None:
                        if local._dynfuture is not None and not local._dynfuture.done():
                            local._dynfuture.set_result(False)
                    for cb in self._discovery_cbs:
                        cb(src, msg.dlc == SHVCAN.DLC.ADDR_ANC_LISTEN)
                case SHVCAN.DLC.ADDR_DISC_LISTEN:
                    for v in self._locals.values():
                        if v.listening:
                            await v.announce()
                case SHVCAN.DLC.ADDR_DISC_IGN:
                    for v in self._locals.values():
                        if not v.listening:
                            await v.announce()
                case SHVCAN.DLC.ADDR_DISC:
                    for v in self._locals.values():
                        await v.announce()
            return

        datalen = len(msg.data)
        if datalen < 1:
            return  # Invalid frame (at least destination must be present)
        local = self._locals.get(msg.data[0])
        if local is None:
            return  # Not for us
        new_peer = False
        peer = local._peers.get(src)
        if peer is None:
            if local._new_peer_callback is None or not first or datalen < 2:
                return  # Not new connection or we don't listen
            new_peer = True
            peer = self.Peer(local, src)
            res = local._new_peer_callback(peer)
            if isinstance(res, collections.abc.Awaitable):
                await res
        match datalen:
            case 1:  # Disconnect
                await peer.queue.put(None)
                del local._peers[src]
                return
            case 2:  # Acknowledgement
                if peer._scounter == msg.data[1] and (ack := peer._acknowledgement):
                    ack.set_result(None)
                return

        last = bool(msg.data[1] & 0x80)
        counter = msg.data[1] & 0x7F
        if first:
            peer._rdata.clear()  # Make sure that we start new message
        elif not peer._rdata or counter == peer._rcounter:
            return  # We don't have start or copy of previous message
        elif counter != ((peer._rcounter + 1) % 0x80):
            return peer._rdata.clear()  # Missed frame or message abort
        peer._rcounter = msg.data[1]
        peer._rdata.extend(msg.data[2:])
        if first:
            await self._send_frames((peer._acknowledgementframe(),))
        if last:
            # We ignore here an initial reset message if this is a new peer.
            if not new_peer or peer._rdata != b"\0":
                await peer.queue.put(
                    bytes(peer._rdata)
                    if len(peer._rdata) <= 8
                    else peer._rdata.rstrip(b"\0")
                )
            peer._rdata.clear()

    async def _send_frames(self, frames: collections.abc.Iterable[can.Message]) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._sendexecutor, self.__send_frames, frames)

    def __send_frames(self, frames: collections.abc.Iterable[can.Message]) -> None:
        for msg in frames:
            while True:
                try:
                    self.bus.send(msg)
                except can.exceptions.CanOperationError as exc:
                    if f"[Error Code {errno.ENOBUFS}]" in exc.args[0]:
                        time.sleep(0.01)
                    elif "Transmit buffer full" != exc.args[0]:
                        raise exc
                else:
                    break

    @classmethod
    def socketcan(cls, interface: str) -> SHVCAN:
        """Get :class:`SHVCAN` for given socket CAN interface."""
        return cls(channel=interface, interface="socketcan", fd=True)

    @classmethod
    def virtualcan(cls, name: str) -> SHVCAN:
        """Get :class:`SHVCAN` for given virtual interface name.

        This virtual interface should be used primarilly for the testing of the
        CAN functionality. It works only in single process.
        """
        return cls(name, interface="virtual", protocol=can.CanProtocol.CAN_FD)


class RpcClientCAN(RpcClient):
    """RPC client communicating over CAN bus.

    :param location: The interface to be used for SHV CAN or directly
      :class:`SHVCAN` instance.
    :param address: Address of the peer client should connect to.
    :param client_address: Local address to be used. Note that only values
      from ``0`` to ``127`` are allowed. The higher addresses can be used only
      if you pass ``None`` and in such case a random dynamic address is used
      instead.
    """

    def __init__(
        self, location: str | SHVCAN, address: int, client_address: int | None = None
    ) -> None:
        if not 0 <= address < 256:
            raise ValueError(f"Invalid address: {address}")
        if client_address is not None and not 0 <= client_address < 128:
            raise ValueError(f"Invalid static client address: {client_address}")
        super().__init__()
        self._shvcan: SHVCAN = (
            location if isinstance(location, SHVCAN) else SHVCAN.socketcan(location)
        )
        self._address = address
        self._client_address = client_address
        self._peer: SHVCAN.Peer | None = None
        self._disconect_task: asyncio.Task | None = None
        self._disconnect_event = asyncio.Event()

    @property
    def shvcan(self) -> SHVCAN:
        """Access to the associated :class:`SHVCAN`."""
        return self._shvcan

    def __str__(self) -> str:
        return f"can://{self._shvcan}:{self._address}[{self._client_address}]"

    @property
    def address(self) -> int:
        """The CAN address client is connected to."""
        return self._address

    @property
    def client_address(self) -> int | None:
        """The local CAN address assigned to this client."""
        if self._client_address is not None or self._peer is None:
            return self._client_address
        return self._peer.local.address

    async def _send(self, msg: bytes) -> None:
        if self._peer is None:
            raise EOFError("Not connected")
        await self._peer.send(msg)

    async def _receive(self) -> bytes:
        if self._peer is None:
            raise EOFError("Not connected")
        res = await self._peer.queue.get()
        self._peer.queue.task_done()
        if res is None:
            raise EOFError("Peer disconnected")
        return res

    async def reset(self) -> None:  # noqa: D102
        if not self.connected:
            if self._client_address is None:
                local = await self._shvcan.dynamic_local()
            else:
                try:
                    local = self._shvcan.existing_local(self._client_address)
                except KeyError:
                    local = SHVCAN.Local(self._shvcan, self._client_address)
            self._peer = SHVCAN.Peer(local, self._address)
            logger.debug("%s: Connected", self)
        # Always send reset message to establish connection right away
        await super().reset()

    @property
    def connected(self) -> bool:  # noqa: D102
        return self._peer is not None and self._peer.connected

    def _disconnect(self) -> None:
        if self._peer is not None and self._disconect_task is None:
            self._disconnect_task = asyncio.create_task(self._peer.disconnect())
            self._disconnect_event.set()

    async def wait_disconnect(self) -> None:  # noqa D027
        if self._peer is not None:
            await self._disconnect_event.wait()
            await self._disconnect_task


class RpcServerCAN(RpcServer):
    """RPC server listening on CAN bus.

    :param client_connected_cb: Callable that is called when new client is
      connected.
    :param location: The interface to be used for SHV CAN or directly
      :class:`SHVCAN` instance.
    :param address: Static listening address or ``None`` if a random dynamic
      address should be acquired.
    """

    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], collections.abc.Awaitable[None] | None
        ],
        location: str | SHVCAN,
        address: int | None = None,
    ) -> None:
        if address is not None and not 0 <= address < 128:
            raise ValueError(f"Invalid static address: {address}")
        self.client_connected_cb = client_connected_cb
        """Callback that is called when new client is connected."""
        self._shvcan: SHVCAN = (
            location if isinstance(location, SHVCAN) else SHVCAN.socketcan(location)
        )
        """Associated instance of :class:`SHVCAN`."""
        self._address = address
        """The address server is listening on."""
        self._local: SHVCAN.Local | None = None
        self._clients: weakref.WeakSet[RpcServerCAN.Client] = weakref.WeakSet()
        self._close_event = asyncio.Event()

    @property
    def shvcan(self) -> SHVCAN:
        """Access to the associated :class:`SHVCAN`."""
        return self._shvcan

    def __str__(self) -> str:
        return f"server.can://{self._shvcan}:{self._address}"

    @property
    def address(self) -> int | None:
        """The CAN address assigned to this server."""
        if self._address is not None or self._local is None:
            return self._address
        return self._local.address

    def is_serving(self) -> bool:  # noqa: D102
        return self._local is not None and self._local.listening

    async def listen(self) -> None:  # noqa: D102
        if not self.is_serving():
            if self._address is None:
                self._local = await self._shvcan.dynamic_local()
            else:
                self._local = self._shvcan.static_local(self._address)
            await self._local.bind(self._peer_connect)
            self._close_event.clear()
            logger.debug("%s: Listening", self)

    async def listen_forever(self) -> None:  # noqa: D102
        await self.listen()
        await self.wait_terminated()

    async def _peer_connect(self, peer: SHVCAN.Peer) -> None:
        client = self.Client(peer, self)
        self._clients.add(client)
        res = self.client_connected_cb(client)
        if isinstance(res, collections.abc.Awaitable):
            await res

    def close(self) -> None:  # noqa: D102
        if self.is_serving():
            assert self._local is not None
            self._local.unbind()
            self._close_event.set()
            logger.debug("%s: No longer listening", self)

    async def wait_closed(self) -> None:  # noqa: D102
        if self._local is not None:
            await self._close_event.wait()
            if not self._local._peers:
                await self._local.deactivate()
            self._local = None

    def terminate(self) -> None:  # noqa: D102
        self.close()
        for client in self._clients:
            client.disconnect()

    async def wait_terminated(self) -> None:  # noqa: D102
        await self.wait_closed()
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

        def __init__(self, peer: SHVCAN.Peer, server: RpcServerCAN) -> None:
            super().__init__()
            self._peer: SHVCAN.Peer = peer
            self._server = server
            self._disconect_task: asyncio.Task | None = None
            self._disconnect_event = asyncio.Event()

        @property
        def server(self) -> RpcServerCAN:
            """Access to the associated server."""
            return self._server

        def __str__(self) -> str:
            return f"can://{self._server._shvcan}:{self._peer.address}[{self._peer.local.address}]"

        @property
        def address(self) -> int:
            """The CAN address client is connected to."""
            res = self._server.address
            assert res is not None
            return res

        @property
        def client_address(self) -> int:
            """The local CAN address assigned to this client."""
            return self._peer.address

        async def _send(self, msg: bytes) -> None:
            await self._peer.send(msg)

        async def _receive(self) -> bytes:
            res = await self._peer.queue.get()
            self._peer.queue.task_done()
            if res is None:
                raise EOFError("Peer disconnected")
            return res

        @property
        def connected(self) -> bool:  # noqa: D102
            return self._peer.connected

        def _disconnect(self) -> None:
            if self._peer is not None and self._disconect_task is None:
                self._disconnect_task = asyncio.create_task(self._peer.disconnect())
                self._disconnect_event.set()

        async def wait_disconnect(self) -> None:  # noqa D027
            if self._peer is not None:
                await self._disconnect_event.wait()
                await self._disconnect_task
