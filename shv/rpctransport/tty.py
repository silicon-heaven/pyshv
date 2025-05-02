"""Connection over serial device."""

import asyncio
import collections.abc
import contextlib
import logging
import pathlib

import aioserial

from .abc import RpcClient, RpcServer
from .stream import (
    RpcProtocolSerialCRC,
    RpcTransportProtocol,
)

try:
    import asyncinotify
except (ImportError, TypeError):  # pragma: no cover
    asyncinotify = None  # type: ignore

logger = logging.getLogger(__name__)


class RpcClientTTY(RpcClient):
    """RPC connection to some SHV peer over serial communication device."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        protocol: type[RpcTransportProtocol] = RpcProtocolSerialCRC,
    ) -> None:
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.protocol = protocol
        self.serial: aioserial.AioSerial | None = None
        self._eof = asyncio.Event()
        self._eof.set()

    def __str__(self) -> str:
        return f"tty:{self.port}"

    async def _send(self, msg: bytes) -> None:
        assert self.serial is not None
        await self.serial.write_async(self.protocol.annotate(msg))

    async def _receive(self) -> bytes:
        return await self.protocol.receive(self._read_exactly)

    @property
    def connected(self) -> bool:  # noqa: D102
        return self.serial is not None and self.serial.is_open

    async def reset(self) -> None:  # noqa: D102
        if not self.connected:
            self.serial = aioserial.AioSerial(
                port=self.port,
                baudrate=self.baudrate,
                rtscts=True,
                dsrdtr=True,
                exclusive=True,
            )
            self._eof.clear()
            logger.debug("%s: Connected", self)
        await super().reset()

    async def _read_exactly(self, n: int) -> bytes:
        assert self.serial is not None
        res = bytearray()
        while len(res) < n:
            try:
                res += await self.serial.read_async(n - len(res))
            # Note: TypeError is raised because serial.close() clears some
            # variables that are still used in the task. This is bug in
            # aioserial.
            except (aioserial.SerialException, TypeError) as exc:
                self._eof.set()
                raise EOFError from exc
        return res

    def _disconnect(self) -> None:
        if self.connected:
            assert self.serial is not None
            self.serial.close()
            self._eof.set()

    async def wait_disconnect(self) -> None:  # noqa: D102
        await self._eof.wait()


class RpcServerTTY(RpcServer):
    """RPC server waiting for TTY to appear.

    This actually only maintains a single client as there can't be more than one
    client on single TTY.
    """

    def __init__(
        self,
        client_connected_cb: collections.abc.Callable[
            [RpcClient], collections.abc.Awaitable[None] | None
        ],
        port: str,
        baudrate: int = 115200,
        protocol: type[RpcTransportProtocol] = RpcProtocolSerialCRC,
    ) -> None:
        self.client_connected_cb = client_connected_cb
        """Callbact that is called when new client is connected."""
        self.client = RpcClientTTY(port, baudrate, protocol)
        """The :class:`RpcClientTTY` instance."""
        self._task: asyncio.Task | None = None

    def __str__(self) -> str:
        return f"server.tty:{self.client.port}"

    async def _loop(self) -> None:
        while True:
            try:
                await self.client.reset()
            except OSError as exc:
                logger.debug("%s: Waiting for accessible TTY device: %s", self, exc)
            else:
                logger.debug("%s: Openned", self)
                res = self.client_connected_cb(self.client)
                if isinstance(res, collections.abc.Awaitable):
                    await res
                await self.client.wait_disconnect()
                continue
            if asyncinotify is not None:
                with asyncinotify.Inotify() as inotify:
                    pth = pathlib.Path(self.client.port)
                    inotify.add_watch(
                        pth.parent, asyncinotify.Mask.CREATE | asyncinotify.Mask.ATTRIB
                    )
                    async for event in inotify:
                        if str(pth.name) == str(event.name):
                            break
            else:
                await asyncio.sleep(5)  # type: ignore

    def is_serving(self) -> bool:  # noqa: D102
        return self._task is not None and not self._task.done()

    async def listen(self) -> None:  # noqa: D102
        if not self.is_serving():
            self._task = asyncio.create_task(self._loop())

    async def listen_forewer(self) -> None:  # noqa: D102
        await self.listen()
        await self.wait_closed()

    def close(self) -> None:  # noqa: D102
        if self._task is not None:
            self._task.cancel()

    async def wait_closed(self) -> None:  # noqa: D102
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    def terminate(self) -> None:  # noqa D102
        self.close()
        self.client.disconnect()

    async def wait_terminated(self) -> None:  # noqa D102
        await self.wait_closed()
        await self.client.wait_disconnect()
