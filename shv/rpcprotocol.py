"""Protocols for :class:`RpcClient`."""
import abc
import asyncio
import binascii
import collections.abc
import logging

from .chainpack import ChainPack

logger = logging.getLogger(__name__)


class RpcTransportProtocol(abc.ABC):
    """Base for the implementations of RPC transport protocols."""

    def __init__(
        self,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
    ) -> None:
        self.read = read
        self.write = write

    @abc.abstractmethod
    async def send(self, msg: bytes) -> None:
        """Send message.

        :param msg: Bytes of a complete message to be sent.
        """

    @abc.abstractmethod
    async def receive(self) -> bytes:
        """Receive message.

        :return: Bytes of complete message.
        :raise EOFError: when EOF is encountered.
        """


def protocol_for_asyncio_stream(
    protocol_factory: collections.abc.Callable[
        [
            collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
            collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        ],
        RpcTransportProtocol,
    ],
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> RpcTransportProtocol:
    """Initialize :class:`RpcTransportProtocol` from Asyncio's streams.

    :param protocol_factory: Callable that initializes protocol.
    :param reader: Asyncio's stream reader.
    :param writer: Asyncio's stream writer.
    :return: Transport protocol instance that uses provided streams.
    """

    async def read(n: int) -> bytes:
        try:
            return await reader.readexactly(n)
        except (asyncio.IncompleteReadError, ConnectionError) as exc:
            raise EOFError from exc

    async def write(d: bytes) -> None:
        writer.write(d)
        await writer.drain()

    return protocol_factory(read, write)


class RpcProtocolStream(RpcTransportProtocol):
    """SHV RPC Stream protocol."""

    async def send(self, msg: bytes) -> None:
        await self.write(ChainPack.pack_uint_data(len(msg)))
        await self.write(msg)

    async def receive(self) -> bytes:
        sdata = bytearray()
        while True:
            sdata += await self.read(1)
            try:
                size = ChainPack.unpack_uint_data(sdata)
            except ValueError:
                pass
            else:
                return await self.read(size)


class _RpcProtocolSerial(RpcTransportProtocol):
    """SHV RPC Serial protocol."""

    STX = 0xA2
    ETX = 0xA3
    ATX = 0xA4
    ESC = 0xAA
    ESCMAP = {0x02: STX, 0x03: ETX, 0x04: ATX, 0x0A: ESC}
    ESCRMAP = {v: k for k, v in ESCMAP.items()}

    @classmethod
    def escape(cls, data: bytes) -> bytes:
        """Escape bytes as defined for serial protocol.

        :param data: Data to be escaped (node that you can pass
          :class:`bytearray` to modify in place).
        :return: The modified data.
        """
        # Warning: ESC must be first in the list so we first replace all occurances of
        # ESC before we insert more of them.
        for b in (cls.ESC, cls.STX, cls.ETX, cls.ATX):
            data = data.replace(bytes((b,)), bytes((cls.ESC, cls.ESCRMAP[b])))
        return data

    @classmethod
    def deescape(cls, data: bytes) -> bytes:
        """Reverse escape operation on bytes as defined for serial protocol.

        :param data: Escaped data (node that you can pass :class:`bytearray` to
          modify in place).
        :return: The modified data.
        """
        for b in (cls.STX, cls.ETX, cls.ATX, cls.ESC):
            data = data.replace(bytes((cls.ESC, cls.ESCRMAP[b])), bytes((b,)))
        return data

    def __init__(
        self,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
    ) -> None:
        super().__init__(read, write)
        self.use_crc = False

    async def send(self, msg: bytes) -> None:
        await self.write(bytes((self.STX,)))
        escmsg = self.escape(msg)
        await self.write(escmsg)
        await self.write(bytes((self.ETX,)))
        if self.use_crc:
            await self.write(self.escape(binascii.crc32(escmsg).to_bytes(4, "big")))

    async def receive(self) -> bytes:
        while True:
            while (await self.read(1))[0] != self.STX:
                pass
            data = bytearray()
            while (b := (await self.read(1))[0]) not in (self.ETX, self.ATX):
                data += bytes((b,))
            if b != self.ETX:
                continue
            if self.use_crc:
                crc32_br = bytearray()
                while len(crc32_br) < (siz := 4 + crc32_br.count(bytes((self.ESC,)))):
                    crc32_br += await self.read(siz - len(crc32_br))
                crc32_b = self.deescape(crc32_br)
                if int.from_bytes(crc32_b, "big") != binascii.crc32(data):
                    continue
            return self.deescape(data)


class RpcProtocolSerial(_RpcProtocolSerial):
    """SHV RPC Serial protocol."""


class RpcProtocolSerialCRC(_RpcProtocolSerial):
    """SHV RPC Serial protocol with CRC32 message validation."""

    def __init__(
        self,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
    ) -> None:
        super().__init__(read, write)
        self.use_crc = True
