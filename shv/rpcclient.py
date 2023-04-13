"""RPC connection, that includes client and specific server connection."""
from __future__ import annotations

import asyncio
import enum
import logging
import typing

from .chainpack import ChainPack, ChainPackReader, ChainPackWriter
from .cpcontext import UnpackContext
from .cpon import Cpon, CponReader, CponWriter
from .rpcmessage import RpcMessage
from .rpcprotocol import RpcProtocol

logger = logging.getLogger(__name__)


def get_next_rpc_request_id():
    RpcClient.lastRequestId += 1
    return RpcClient.lastRequestId


class RpcClient:
    """RPC connection to some SHV peer.

    You most likely want to use `connect` or `connect_device` class methods
    instead of initializing this class directly.

    :param reader: Reader for the connection to the SHV RPC server.
    :param writer: Writer for the connection to the SHV RPC server.
    """

    class MethodCallError(Exception):
        def __init__(self, error):
            self.error = error

        def __str__(self):
            return CponWriter.pack(self.error).decode()

    class LoginType(enum.Enum):
        """Enum specifying which login type should be used."""

        PLAIN = "PLAIN"
        """Plain login format should be used."""
        SHA1 = "SHA1"
        """Use hash algorithm SHA1 (preferred and common default)."""
        NONE = None
        """No login type thus perform no login."""

    lastRequestId = 0

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        self.read_data = bytearray(0)
        self.reader = reader
        self.writer = writer

    @classmethod
    async def connect(
        cls,
        host: str | None,
        port: int = 3755,
        protocol: RpcProtocol = RpcProtocol.TCP,
        user: str | None = None,
        password: str | None = None,
        login_type: LoginType = LoginType.SHA1,
        login_options: dict[str, typing.Any] = {"idleWatchDogTimeOut": 0},
    ) -> RpcClient:
        """Connect and login to the SHV RPC server.

        :param host: IP/Hostname (TCP) or socket path (LOCKAL_SOCKET)
        :param port: Port (TCP) to connect to
        :param protocol: Protocol used to connect to the server
        :param user: User name used to login
        :param password: Password used to login
        :param login_type: Type of the login to be used
        :param login_options: Options sent with login
        :returns: Connected and logged in SHV RPC client handle
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

        if login_type is cls.LoginType.NONE:
            return client

        await client.call_shv_method(None, "hello")
        await client.read_rpc_message()
        params = {
            "login": {"password": password, "type": login_type.value, "user": user},
            "options": login_options,
        }
        logger.debug("LOGGING IN")
        await client.call_shv_method(None, "login", params)
        await client.read_rpc_message()
        logger.debug("LOGGED IN")
        return client

    @classmethod
    async def connect_device(
        cls,
        host: str | None,
        port: int = 3755,
        protocol: RpcProtocol = RpcProtocol.TCP,
        user: str | None = None,
        password: str | None = None,
        login_type: LoginType = LoginType.SHA1,
        device_id: int | None = None,
        mount_point: str | None = None,
    ) -> RpcClient:
        """Connect and login to the SHV RPC server when being device.

        This is variant of `connect` class method that should be used when
        connecting a new device to the broker.

        The parameters are the same as in case of `connect` with exception of
        the documented ones.

        :param device_id: Identifier of this device
        :param mount_point: Path the device should be mounted to
        """
        return await cls.connect(
            host,
            port,
            protocol,
            user,
            password,
            login_type,
            {
                "device": {
                    **({"deviceId": device_id} if device_id is not None else {}),
                    **({"mountPoint": mount_point} if mount_point is not None else {}),
                },
            },
        )

    async def call_shv_method(self, shv_path, method, params=None) -> int:
        """Call the given SHV method on given path.

        :param shv_path: Path to the node with requested method
        :param method: Name of the method to call
        :param params: Parameters passed to the method
        :returns: assigned request ID you can use to identify the response
        """
        rid = get_next_rpc_request_id()
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
        data = msg.to_chainpack()
        logger.debug("<== SND: %s", msg.to_string())

        writter = ChainPackWriter()
        writter.write_uint_data(len(data) + 1)
        self.writer.write(writter.ctx.data_bytes())
        self.writer.write(ChainPack.ProtocolType.to_bytes(1, "big"))
        self.writer.write(data)
        await self.writer.drain()

    def _get_rpc_msg(self):
        if len(self.read_data) < 6:
            return None
        try:
            rd = ChainPackReader(self.read_data)
            size = rd.read_uint_data()
            packet_len = size + rd.ctx.index
        except UnpackContext.BufferUnderflow:
            return None
        if packet_len > len(self.read_data):
            return None
        proto = rd.ctx.get_byte()
        if proto == Cpon.ProtocolType:
            rd = CponReader(rd.ctx)
        rpc_val = rd.read()
        self.read_data = self.read_data[packet_len:]
        return RpcMessage(rpc_val)

    async def read_rpc_message(
        self, throw_error: bool = True
    ) -> typing.Optional[RpcMessage]:
        """Read next received RPC message or wait for next to be received.

        :param throw_error: If MethodCallError should be raised or not.
        :returns: Next RPC message is returned or `None` in case of EOF.
        :raises RpcClient.MethodCallError: When mesasge is error.
        """
        while not self.reader.at_eof():
            msg = self._get_rpc_msg()
            if msg:
                logger.debug("==> REC: %s", msg.to_string())
                if throw_error and msg.error():
                    raise RpcClient.MethodCallError(msg.error())
                return msg
            data = await self.reader.read(1024)
            self.read_data += data
        return None
