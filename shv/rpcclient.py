"""RPC connection, that includes client and specific server connection."""
from __future__ import annotations

import asyncio
import io
import logging
import time
import typing

from .chainpack import ChainPack, ChainPackReader, ChainPackWriter
from .cpon import Cpon, CponReader
from .rpcmessage import RpcMessage
from .rpcurl import RpcProtocol

logger = logging.getLogger(__name__)


class RpcClient:
    """RPC connection to some SHV peer.

    You most likely want to use :func:`connect` class methods instead of
    initializing this class directly.

    :param reader: Reader for the connection to the SHV RPC server.
    :param writer: Writer for the connection to the SHV RPC server.
    """

    lastRequestId: typing.ClassVar[int] = 0
    """Counter of request IDs to ensure that every request has unique ID."""

    @classmethod
    def next_request_id(cls) -> int:
        """Provides you with unique request identifier.

        The identifier won't repeat for this application as it is just simple
        counter that should never wrap.
        """
        cls.lastRequestId += 1
        return cls.lastRequestId

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        self.last_activity = time.monotonic()
        """Last activity on this connection (read or write of the message)."""
        self.reader = reader
        self.writer = writer
        self._read_data = bytearray(0)

    @classmethod
    async def connect(
        cls,
        host: str | None,
        port: int = 3755,
        protocol: RpcProtocol = RpcProtocol.TCP,
    ) -> RpcClient:
        """Connect to the SHV RPC server.

        :param host: IP/Hostname (TCP) or socket path (LOCKAL_SOCKET)
        :param port: Port (TCP) to connect to
        :param protocol: Protocol used to connect to the server
        """
        if host is None:
            if protocol == RpcProtocol.TCP:
                host = "localhost"
            elif protocol == RpcProtocol.LOCAL_SOCKET:
                host = "shv.sock"
            else:
                raise RuntimeError(f"Invalid protocol: {protocol}")
        logger.debug("Connecting to: %s:%d", host, port)
        if protocol == RpcProtocol.TCP:
            reader, writer = await asyncio.open_connection(host, port)
        elif protocol == RpcProtocol.LOCAL_SOCKET:
            reader, writer = await asyncio.open_unix_connection(host)
        client = cls(reader, writer)
        logger.debug("%s CONNECTED", str(protocol))
        return client

    async def call_shv_method(self, shv_path, method, params=None) -> int:
        """Call the given SHV method on given path.

        :param shv_path: Path to the node with requested method
        :param method: Name of the method to call
        :param params: Parameters passed to the method
        :return: assigned request ID you can use to identify the response
        """
        rid = self.next_request_id()
        await self.call_shv_method_with_id(rid, shv_path, method, params)
        return rid

    async def call_shv_method_with_id(
        self, req_id, shv_path, method, params=None
    ) -> None:
        """Call the given SHV method on given path with specific request ID.

        :param req_id: Request ID used to submit the method call with.
        :param shv_path: Path to the node with requested method
        :param method: Name of the method to call
        :param params: Parameters passed to the method
        """
        msg = RpcMessage()
        msg.set_shv_path(shv_path)
        msg.set_method(method)
        msg.set_params(params)
        msg.set_request_id(req_id)
        await self.send_rpc_message(msg)

    async def send_rpc_message(self, msg: RpcMessage) -> None:
        """Send the given SHV RPC Message.

        :param msg: Message to be sent
        """
        logger.debug("<== SND: %s", msg.to_string())

        data = msg.to_chainpack()
        writer = ChainPackWriter(self.writer)
        writer.write_uint_data(len(data) + 1)
        self.writer.write(ChainPack.ProtocolType.to_bytes(1, "big"))
        self.writer.write(data)
        await self.writer.drain()
        self.last_activity = time.monotonic()

    def _get_rpc_msg(self):
        if len(self._read_data) < 6:
            return None
        try:
            rd = ChainPackReader(io.BytesIO(self._read_data))
            size = rd.read_uint_data()
            packet_len = size + rd.bytes_cnt
        except EOFError:
            return None
        if packet_len > len(self._read_data):
            return None
        proto = rd.read_raw(1)
        if len(proto) == 1 and proto[0] == Cpon.ProtocolType:
            rd = CponReader(rd)
        rpc_val = rd.read()
        self._read_data = self._read_data[packet_len:]
        return RpcMessage(rpc_val)

    async def read_rpc_message(
        self, throw_error: bool = True
    ) -> typing.Optional[RpcMessage]:
        """Read next received RPC message or wait for next to be received.

        :param throw_error: If RpcError should be raised or not.
        :return: Next RPC message is returned or `None` in case of EOF.
        :raise RpcError: When mesasge is error and `throw_error` is `True`.
        """
        while not self.reader.at_eof():
            msg = self._get_rpc_msg()
            self.last_activity = time.monotonic()
            if msg:
                logger.debug("==> REC: %s", msg.to_string())
                if throw_error and msg.is_error():
                    raise msg.rpc_error()
                return msg
            data = await self.reader.read(1024)
            self._read_data += data
        return None

    async def disconnect(self):
        """Close the connection."""
        self.writer.close()
        await self.writer.wait_closed()
