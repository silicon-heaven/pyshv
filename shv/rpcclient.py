"""RPC connection, that includes client and specific server connection."""
from __future__ import annotations

import asyncio
import enum
import io
import logging
import typing

from .chainpack import ChainPack, ChainPackReader, ChainPackWriter
from .cpon import Cpon, CponReader
from .rpcmessage import RpcMessage
from .rpcprotocol import RpcProtocol

logger = logging.getLogger(__name__)


class RpcClient:
    """RPC connection to some SHV peer.

    You most likely want to use `connect` or `connect_device` class methods
    instead of initializing this class directly.

    :param reader: Reader for the connection to the SHV RPC server.
    :param writer: Writer for the connection to the SHV RPC server.
    """

    class LoginType(enum.Enum):
        """Enum specifying which login type should be used."""

        PLAIN = "PLAIN"
        """Plain login format should be used."""
        SHA1 = "SHA1"
        """Use hash algorithm SHA1 (preferred and common default)."""

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
        self.reader = reader
        self.writer = writer
        self.callback: typing.Callable[
            [RpcClient, RpcMessage], typing.Awaitable | None
        ] | None = None
        self._read_data = bytearray(0)
        self._client_id: int | None = None

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

    def client_id(self) -> int | None:
        """Provides current client ID.

        :returns: client ID or None in case login wasn't performed yet.
        """
        return self._client_id

    async def login(
        self,
        user: str | None = None,
        password: str | None = None,
        login_type: LoginType = LoginType.SHA1,
        login_options: dict[str, typing.Any] | None = {"idleWatchDogTimeOut": 36000},
    ) -> None:
        """Perform login to the broker.

        The login need to be performed only once right after the connection is
        established.

        :param user: User name used to login
        :param password: Password used to login
        :param login_type: Type of the login to be used
        :param login_options: Options sent with login
        :returns: Connected and logged in SHV RPC client handle
        :raises RpcError: when Rpc message with error is read.
        """
        assert self._client_id is None
        # Note: The implementation here expects that broker won't sent any other
        # messages until login is actually performed. That is what happens but
        # it is not defined in any SHV design document as it seems.
        await self.call_shv_method(None, "hello")
        await self.read_rpc_message()
        params = {
            "login": {"password": password, "type": login_type.value, "user": user},
            "options": login_options,
        }
        logger.debug("LOGGING IN")
        await self.call_shv_method(None, "login", params)
        resp = await self.read_rpc_message()
        if resp is None:
            return
        result = resp.result()
        cid = result.get("clientId", None) if isinstance(result, dict) else None
        if isinstance(cid, int):
            self._client_id = cid
        logger.debug("LOGGED IN")

    async def login_device(
        self,
        user: str | None = None,
        password: str | None = None,
        login_type: LoginType = LoginType.SHA1,
        device_id: int | None = None,
        mount_point: str | None = None,
    ) -> None:
        """Perform login to the broker as a device.

        The parameters are the same as in case of `login` with exception of
        the documented ones.

        :param device_id: Identifier of this device
        :param mount_point: Path the device should be mounted to
        """
        await self.login(
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
        proto = rd.stream_read_byte()
        if proto == Cpon.ProtocolType:
            rd = CponReader(rd)
        rpc_val = rd.read()
        self._read_data = self._read_data[packet_len:]
        return RpcMessage(rpc_val)

    async def read_rpc_message(
        self, throw_error: bool = True
    ) -> typing.Optional[RpcMessage]:
        """Read next received RPC message or wait for next to be received.

        :param throw_error: If RpcError should be raised or not.
        :returns: Next RPC message is returned or `None` in case of EOF.
        :raises RpcError: When mesasge is error and `throw_error` is `True`.
        """
        while not self.reader.at_eof():
            msg = self._get_rpc_msg()
            if msg:
                logger.debug("==> REC: %s", msg.to_string())
                if throw_error and msg.is_error():
                    raise msg.rpc_error()
                return msg
            data = await self.reader.read(1024)
            self._read_data += data
        return None

    async def read_loop(self) -> None:
        """Loop that periodically calls `read_rpc_message`.

        The received messages are passed to `_rpc_message`.
        """
        while not self.writer.is_closing():
            msg = await self.read_rpc_message(throw_error=False)
            if msg is None:
                return
            await self._rpc_message(msg)

    async def _rpc_message(self, msg: RpcMessage) -> None:
        """Handle method that is called for every message from `read_loop`.

        Overload this method to handle messages received in `read_loop`.

        :param msg: Received message.
        """
        if self.callback is not None:
            if asyncio.iscoroutinefunction(self.callback):
                asyncio.create_task(self.callback(self, msg))
            else:
                self.callback(self, msg)

    async def disconnect(self):
        """Close the connection."""
        self.writer.close()
        await self.writer.wait_closed()
