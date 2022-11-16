import asyncio
import logging
from enum import Enum

from .chainpack import ChainPack, ChainPackReader, ChainPackWriter
from .cpcontext import UnpackContext
from .cpon import Cpon, CponReader, CponWriter
from .rpcmessage import RpcMessage

_logger = logging.getLogger("RpcClient")


def get_next_rpc_request_id():
    RpcClient.lastRequestId += 1
    return RpcClient.lastRequestId


class RpcClient:
    class MethodCallError(Exception):
        def __init__(self, error):
            self.error = error

        def __str__(self):
            return CponWriter.pack(self.error).decode()

    class State(Enum):
        Closed = 1
        Connecting = 2
        Connected = 3
        LoggedIn = 4
        ConnectionError = 5

    class LoginType(Enum):
        Plain = "PLAIN"
        Sha1 = "SHA1"

    lastRequestId = 0

    def __init__(self):
        self.state = RpcClient.State.Closed
        self.readData = bytearray(0)
        self.reader = None
        self.writer = None

    async def connect(
        self,
        host,
        port=3755,
        user=None,
        password=None,
        login_type: LoginType = LoginType.Sha1,
        device_id=None,
        mount_point=None,
    ):
        _logger.debug("connecting to: {}:{}".format(host, port))
        self.state = RpcClient.State.Connecting
        self.reader, self.writer = await asyncio.open_connection(host, port)
        self.state = RpcClient.State.Connected
        _logger.debug("TCP CONNECTED")
        await self.call_shv_method(None, "hello")
        await self.read_rpc_message()

        params = {
            "login": {"password": password, "type": login_type.value, "user": user},
            "options": {
                # "device": {
                #     "deviceId": "dev-id"
                #     "mountPoint": "test/agent1"
                # },
                "idleWatchDogTimeOut": 0
            },
        }
        if device_id is not None:
            params["options"]["device"] = {"deviceId": device_id}
        elif mount_point is not None:
            params["options"]["device"] = {"mountPoint": mount_point}
        _logger.debug("LOGGING IN")
        await self.call_shv_method(None, "login", params)
        await self.read_rpc_message()
        _logger.debug("LOGGED IN")
        self.state = RpcClient.State.LoggedIn

    async def call_shv_method(self, shv_path, method, params=None):
        await self.call_shv_method_with_id(
            get_next_rpc_request_id(), shv_path, method, params
        )

    async def call_shv_method_with_id(self, req_id, shv_path, method, params=None):
        msg = RpcMessage()
        msg.set_shv_path(shv_path)
        msg.set_method(method)
        msg.set_params(params)
        msg.set_request_id(req_id)

        await self.send_rpc_message(msg)

    async def send_rpc_message(self, msg):
        data = msg.to_chainpack()
        _logger.debug("<== SND: {}".format(msg.to_string()))

        wr = ChainPackWriter()
        wr.write_uint_data(len(data) + 1)
        self.writer.write(wr.ctx.data_bytes())

        proto = bytearray(1)
        proto[0] = ChainPack.ProtocolType
        self.writer.write(proto)

        self.writer.write(data)

        await self.writer.drain()

    def _get_rpc_msg(self):
        if len(self.readData) < 6:
            return None
        try:
            rd = ChainPackReader(self.readData)
            size = rd.read_uint_data()
            packet_len = size + rd.ctx.index
        except UnpackContext.BufferUnderflow:
            return None
        if packet_len > len(self.readData):
            return None
        proto = rd.ctx.get_byte()
        if proto == Cpon.ProtocolType:
            rd = CponReader(rd.ctx)
        rpc_val = rd.read()
        self.readData = self.readData[packet_len:]
        return RpcMessage(rpc_val)

    async def read_rpc_message(self, throw_error=True):
        while True:
            msg = self._get_rpc_msg()
            if msg:
                _logger.debug("==> REC: {}".format(msg.to_string()))
                if throw_error and msg.error():
                    raise RpcClient.MethodCallError(msg.error())
                return msg
            data = await self.reader.read(1024)
            self.readData += data
