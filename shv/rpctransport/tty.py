"""Connection over serial device."""

import asyncio
import collections.abc
import contextlib
import fcntl
import logging
import os
import pathlib
import termios
import tty
import typing

from .abc import RpcClient, RpcServer
from .stream import RpcClientStream, RpcProtocolSerialCRC

try:
    import asyncinotify
except (ImportError, TypeError):  # pragma: no cover
    asyncinotify = None

logger = logging.getLogger(__name__)


# TODO this is not supported on windows
class RpcClientTTY(RpcClientStream):
    """RPC connection to some SHV peer over serial communication device."""

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
    ) -> None:
        super().__init__(RpcProtocolSerialCRC)
        self.port = port
        try:
            self._bspeed = getattr(termios, f"B{baudrate}")
        except AttributeError as exc:
            raise ValueError(f"Unsupported baudrate {baudrate}") from exc

    def __str__(self) -> str:
        return f"tty:{self.port}"

    async def reset(self) -> None:  # noqa: D102
        was_connected = self.connected
        await super().reset()
        if not was_connected and self.connected:
            await self.reset()  # Nested reset to send reset message

    async def _open_connection(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        loop = asyncio.get_running_loop()

        fd = os.open(self.port, os.O_RDWR)
        try:
            if not os.isatty(fd):
                raise ValueError(f"{self.port} is not TTY")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            attr = termios.tcgetattr(fd)
            _cfmakeraw(attr)
            attr[tty.CFLAG] |= termios.CRTSCTS  # flow control
            attr[tty.ISPEED] = attr[tty.OSPEED] = self._bspeed
            termios.tcsetattr(fd, termios.TCSAFLUSH, attr)
        except Exception:
            os.close(fd)
            raise
        file = os.fdopen(fd, "wb")

        reader = asyncio.StreamReader()
        rprotocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: rprotocol, file)

        wprotocol = asyncio.StreamReaderProtocol(asyncio.StreamReader())
        wtransport, _ = await loop.connect_write_pipe(lambda: wprotocol, file)
        writer = asyncio.StreamWriter(wtransport, wprotocol, None, loop)

        return reader, writer


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
    ) -> None:
        self.client_connected_cb = client_connected_cb
        """Callbact that is called when new client is connected."""
        self.client = RpcClientTTY(port, baudrate)
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
                await asyncio.sleep(5)

    def is_serving(self) -> bool:  # noqa: D102
        return self._task is not None and not self._task.done()

    async def listen(self) -> None:  # noqa: D102
        if not self.is_serving():
            self._task = asyncio.create_task(self._loop())

    async def listen_forever(self) -> None:  # noqa: D102
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


def _cfmakeraw(mode: typing.Any) -> None:  # noqa: ANN401
    """Make termios mode raw.

    License: Python Software Foundation License Version 2
    Source: CPython (tty.py)
    Author: Steen Lumholt.

    This is copy of the code provided in standard Python library since Python
    3.12. The switch to the ``tty.cfmakeraw`` should be made once minimal
    version is at least that.
    """
    # Clear all POSIX.1-2017 input mode flags.
    # See chapter 11 "General Terminal Interface"
    # of POSIX.1-2017 Base Definitions.
    mode[tty.IFLAG] &= ~(
        termios.IGNBRK
        | termios.BRKINT
        | termios.IGNPAR
        | termios.PARMRK
        | termios.INPCK
        | termios.ISTRIP
        | termios.INLCR
        | termios.IGNCR
        | termios.ICRNL
        | termios.IXON
        | termios.IXANY
        | termios.IXOFF
    )

    # Do not post-process output.
    mode[tty.OFLAG] &= ~termios.OPOST

    # Disable parity generation and detection; clear character size mask;
    # let character size be 8 bits.
    mode[tty.CFLAG] &= ~(termios.PARENB | termios.CSIZE)
    mode[tty.CFLAG] |= termios.CS8

    # Clear all POSIX.1-2017 local mode flags.
    mode[tty.LFLAG] &= ~(
        termios.ECHO
        | termios.ECHOE
        | termios.ECHOK
        | termios.ECHONL
        | termios.ICANON
        | termios.IEXTEN
        | termios.ISIG
        | termios.NOFLSH
        | termios.TOSTOP
    )

    # POSIX.1-2017, 11.1.7 Non-Canonical Mode Input Processing,
    # Case B: MIN>0, TIME=0
    # A pending read shall block until MIN (here 1) bytes are received,
    # or a signal is received.
    mode[tty.CC] = list(mode[tty.CC])
    mode[tty.CC][termios.VMIN] = 1
    mode[tty.CC][termios.VTIME] = 0
