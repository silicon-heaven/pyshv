"""Protocols for :class:`RpcClient`."""

import abc
import asyncio
import binascii
import collections.abc
import logging
import typing

from .chainpack import ChainPack

logger = logging.getLogger(__name__)


class RpcTransportProtocol(abc.ABC):
    """Base for the implementations of RPC transport protocols."""

    @classmethod
    @abc.abstractmethod
    async def send(
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
    ) -> None:
        """Send message.

        :param msg: Bytes of a complete message to be sent.
        """

    @classmethod
    @abc.abstractmethod
    async def receive(
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
    ) -> bytes:
        """Receive message.

        :return: Bytes of complete message.
        :raise EOFError: when EOF is encountered.
        """

    @classmethod
    async def asyncio_send(cls, writer: asyncio.StreamWriter, msg: bytes) -> None:
        """Variation on :meth:`send` that uses :class:`asyncio.StreamWriter`."""

        async def write(d: bytes) -> None:
            writer.write(d)
            await writer.drain()

        await cls.send(write, msg)

    @classmethod
    async def asyncio_receive(cls, reader: asyncio.StreamReader) -> bytes:
        """Variation on :meth:`receive` that uses :class:`asyncio.StreamReader`."""

        async def read(n: int) -> bytes:
            try:
                return await reader.readexactly(n)
            except (asyncio.IncompleteReadError, ConnectionError) as exc:
                raise EOFError from exc

        return await cls.receive(read)


class RpcProtocolStream(RpcTransportProtocol):
    """SHV RPC Stream protocol."""

    @classmethod
    async def send(  # noqa: D102
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
    ) -> None:
        await write(ChainPack.pack_uint_data(len(msg)))
        await write(msg)

    @classmethod
    async def receive(  # noqa: D102
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
    ) -> bytes:
        sdata = bytearray()
        while True:
            sdata += await read(1)
            try:
                size = ChainPack.unpack_uint_data(sdata)
            except ValueError:
                pass
            else:
                return await read(size)


class _RpcProtocolSerial(RpcTransportProtocol):
    """SHV RPC Serial protocol."""

    STX = 0xA2
    ETX = 0xA3
    ATX = 0xA4
    ESC = 0xAA
    ESCMAP: typing.Final = {0x02: STX, 0x03: ETX, 0x04: ATX, 0x0A: ESC}
    ESCRMAP: typing.Final = {v: k for k, v in ESCMAP.items()}

    @classmethod
    async def _send(
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
        use_crc: bool,
    ) -> None:
        await write(bytes((cls.STX,)))
        escmsg = cls.escape(msg)
        await write(escmsg)
        await write(bytes((cls.ETX,)))
        if use_crc:
            await write(cls.escape(binascii.crc32(escmsg).to_bytes(4, "big")))

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
    async def _receive(
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
        use_crc: bool,
    ) -> bytes:
        while True:
            while (await read(1))[0] != cls.STX:
                pass
            data = bytearray()
            while (b := (await read(1))[0]) not in {cls.ETX, cls.ATX}:
                data += bytes((b,))
            if b == cls.ATX:
                continue
            if use_crc:
                crc32_br = bytearray()
                while len(crc32_br) < (siz := 4 + crc32_br.count(bytes((cls.ESC,)))):
                    crc32_br += await read(siz - len(crc32_br))
                crc32_b = cls.deescape(crc32_br)
                if int.from_bytes(crc32_b, "big") != binascii.crc32(data):
                    continue
            return cls.deescape(data)

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


class RpcProtocolSerial(_RpcProtocolSerial):
    """SHV RPC Serial protocol."""

    @classmethod
    async def send(  # noqa: D102
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
    ) -> None:
        await cls._send(write, msg, False)

    @classmethod
    async def receive(  # noqa: D102
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
    ) -> bytes:
        return await cls._receive(read, False)


class RpcProtocolSerialCRC(_RpcProtocolSerial):
    """SHV RPC Serial protocol with CRC32 message validation."""

    @classmethod
    async def send(  # noqa: D102
        cls,
        write: collections.abc.Callable[[bytes], collections.abc.Awaitable[None]],
        msg: bytes,
    ) -> None:
        await cls._send(write, msg, True)

    @classmethod
    async def receive(  # noqa: D102
        cls,
        read: collections.abc.Callable[[int], collections.abc.Awaitable[bytes]],
    ) -> bytes:
        return await cls._receive(read, True)
