"""Common base for RPC clients and servers."""

import abc
import enum
import logging
import time
import typing

from ..chainpack import ChainPack
from ..cpon import CponWriter
from ..rpcmessage import RpcMessage
from ..value import SHVIMap

logger = logging.getLogger(__name__)


class RpcClient(abc.ABC):
    """RPC connection to some SHV peer."""

    class Control(enum.Enum):
        """Control message that is received instead of :class:`RpcMessage`."""

        RESET = enum.auto()

    def __init__(self) -> None:
        self.last_send = time.monotonic()
        """Monotonic time when last message was sent on this connection.

        The initial value is time of the RpcClient creation.
        """
        self.last_receive = time.monotonic()
        """Monotonic time when last message was received on this connection.

        The initial value is time of the RpcClient creation.
        """

    @classmethod
    async def connect(cls, *args: typing.Any, **kwargs: typing.Any) -> typing.Self:  # noqa ANN401
        """Connect client.

        This conveniently combines object initialization and call to
        :meth:`reset`. All arguments are passed to the object initialization.
        """
        res = cls(*args, **kwargs)
        await res.reset()
        return res

    async def send(self, msg: RpcMessage) -> None:
        """Send the given SHV RPC Message.

        :param msg: Message to be sent
        :raise EOFError: when client is not connected.
        """
        await self._send(bytearray((ChainPack.ProtocolType,)) + msg.to_chainpack())
        self.last_send = time.monotonic()
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("%s => %s", str(self), msg.to_string())

    @abc.abstractmethod
    async def _send(self, msg: bytes) -> None:
        """Child's implementation of message sending."""

    async def receive(self) -> RpcMessage | Control:
        """Read next received RPC message or wait for next to be received.

        :return: Next RPC message is returned or :class:`Control` for special control
          messages.
        :raise EOFError: in case EOF is encountered.
        """
        while True:
            data = await self._receive()
            self.last_receive = time.monotonic()
            if len(data) > 1:
                if data[0] == ChainPack.ProtocolType:
                    try:
                        shvdata = ChainPack.unpack(data[1:])
                    except ValueError as exc:
                        logger.debug("<= Invalid ChainPack", exc_info=exc)
                    else:
                        if isinstance(shvdata, SHVIMap):
                            if (msg := RpcMessage(shvdata)).is_valid():
                                if logger.isEnabledFor(logging.DEBUG):
                                    logger.debug("%s <= %s", self, msg.to_string())
                                return msg
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                "<= Invalid RPC message: %s",
                                CponWriter.pack(shvdata).decode("UTF-8"),
                            )
            elif len(data) == 1 and data[0] == 0:
                logger.debug("%s <= Control message RESET", self)
                return self.Control.RESET
            elif logger.isEnabledFor(logging.DEBUG):
                logger.debug("%s <= Invalid message received: %s", self, data)

    @abc.abstractmethod
    async def _receive(self) -> bytes:
        """Message receive implementation.

        :return: bytes of received message (complete valid message).
        :raise EOFError: if end of the connection is encountered.
        """

    async def reset(self) -> None:
        """Reset the connection.

        This sends reset to the peer and thus it is instructed to forget anything that
        might have been associated with this client.

        This can also try reconnect if client supports it.

        This can raise not only :class:`EOFError` but also other exception based
        on the client implementation.

        :raise EOFError: if peer is not connected and reconnect is not either supported
          or possible.
        """
        await self._send(bytes((0,)))
        logger.debug("%s => Control message RESET", self)

    @property
    @abc.abstractmethod
    def connected(self) -> bool:
        """Check if client is still connected.

        This is only local check. There is no communication done and thus depending on
        the transport layer this can be pretty much a lie. The only reliable tests is
        sending request and receiving respond to it.

        :return: ``True`` if client might still connected and ``False`` if we know that
            it is not.
        """

    def disconnect(self) -> None:
        """Close the connection."""
        if self.connected:
            logger.debug("%s: Disconnecting", self)
        self._disconnect()

    @abc.abstractmethod
    def _disconnect(self) -> None:
        """Child's implementation of message sending."""

    async def wait_disconnect(self) -> None:  # noqa D027
        """Wait for the client's disconnection."""


class RpcServer(abc.ABC):
    """RPC server listening for new SHV connections."""

    @abc.abstractmethod
    def is_serving(self) -> bool:
        """Check if server is accepting new SHV connections.

        :return: ``True`` if new connection can be accepted and ``False``
          otherwise.
        """

    @abc.abstractmethod
    async def listen(self) -> None:
        """Start accepting new SHV connections."""

    @abc.abstractmethod
    async def listen_forewer(self) -> None:
        """Listen and block the calling coroutine until cancelation."""

    @abc.abstractmethod
    def close(self) -> None:
        """Stop accepting new SHV connections."""

    @abc.abstractmethod
    async def wait_closed(self) -> None:
        """Wait for the server closure."""

    @abc.abstractmethod
    def terminate(self) -> None:
        """Terminate the server.

        This disconnects all accepted clients as well as stops accepting new SHV
        connections.
        """

    @abc.abstractmethod
    async def wait_terminated(self) -> None:
        """Wait for the server termination."""
