"""Common state for the RPC broker that works as server in the SHV network."""
import asyncio
import collections.abc
import enum
import importlib.metadata
import itertools
import logging
import random
import time
import typing

from ..rpcclient import RpcClient
from ..rpcerrors import (
    RpcError,
    RpcErrorCode,
    RpcInvalidParamsError,
    RpcMethodCallExceptionError,
)
from ..rpcmessage import RpcMessage
from ..rpcmethod import RpcMethodAccess, RpcMethodDesc
from ..rpcserver import RpcServer, create_rpc_server
from ..rpcsubscription import RpcSubscription
from ..rpcurl import RpcLoginType
from ..simpleclient import SimpleClient
from ..value import SHVType
from ..value_tools import shvget
from .rpcbrokerconfig import RpcBrokerConfig

logger = logging.getLogger(__name__)


class RpcBroker:
    """SHV RPC broker.

    The broker manages multiple RpcClient instances and exchanges messages
    between them.
    """

    def __init__(self, config: RpcBrokerConfig) -> None:
        self.clients: dict[int, RpcBroker.Client] = {}
        """Mapping from client IDs to client objects."""
        self.config = config
        """Configuration of the RPC Broker."""
        self.servers: dict[str, RpcServer] = {}
        """All servers managed by Broker where keys are their configured names."""
        self.__next_caller_id = 0

    def next_caller_id(self) -> int:
        """Allocate new caller ID."""
        # TODO try to reuse older caller IDs to send smaller messages but we need to do
        # it only after some given delay. We can safe time of client disconnect to the
        # self.clients and use that to identify when we can reuse caller id.
        self.__next_caller_id += 1
        return self.__next_caller_id - 1

    def add_client(self, client: RpcClient) -> "RpcBroker.Client":
        """Add a new client to be handled by the broker.

        :param client: RPC client instance to be handled by broker.
        :return: The client instance in the broker.
        """
        cid = self.next_caller_id()
        self.clients[cid] = self.Client(client, self, cid)
        logger.info("Client registered to broker with ID: %s", cid)
        return self.clients[cid]

    def get_client(self, cid: int | str) -> typing.Union["RpcBroker.Client", None]:
        """Lookup client with given ID.

        :param cid: ID of the client either as string or as integer.
        :return: :class:`RpcBroker.Client` when such client is located and ``None``
            otherwise.
        """
        try:
            return self.clients[cid if isinstance(cid, int) else int(cid, 10)]
        except (ValueError, KeyError):
            return None

    def client_on_path(self, path: str) -> tuple["RpcBroker.Client", str] | None:
        """Locate client mounted on given path.

        :return: client associated with this mount point and path relative to
            the client or None if there is no such client.
        """
        if path.startswith(".app/broker/client/"):
            pth = path.split("/")
            client = self.get_client(pth[3])
            return (client, "/".join(pth[4:])) if client else None

        # Note: we do not allow recursive mount points and thus first match is the
        # correct and the only client.
        for c in self.clients.values():
            mp = c.mount_point
            if (
                mp
                and path.startswith(mp)
                and (len(path) == len(mp) or path[len(mp)] == "/")
            ):
                return c, path[len(c.mount_point or "") + 1 :]
        return None

    async def start_serving(self) -> None:
        """Start accepting connectons on all configured servers."""

        def add(client: RpcClient) -> None:
            self.add_client(client)

        for name, url in self.config.listen.items():
            if name not in self.servers:
                self.servers[name] = await create_rpc_server(add, url)

    async def signal(self, msg: RpcMessage) -> None:
        """Send signal to the broker's clients.

        :param msg: Signal message to be sent.
        """
        msgaccess = msg.rpc_access or RpcMethodAccess.READ
        for client in self.clients.values():
            if client.user is None:
                continue
            access = client.user.access_level(msg.path, msg.method)
            if (
                access is not None
                and access >= msgaccess
                and any(s.applies(msg.path, msg.method) for s in client.subscriptions)
            ):
                await client.client.send(msg)

    async def serve_forever(self) -> None:
        """Serve all configured servers and block.

        This is a convenient coroutine that you can use to block main task until broker
        termination. You do not have to await this coroutine to run broker, awaiting on
        :meth:`start_serving` and keeping the loop running is enough to get broker
        working.
        """
        await self.start_serving()
        await asyncio.gather(
            *(server.wait_closed() for server in self.servers.values()),
            return_exceptions=True,
        )
        # TODO handle returned errors

    def close(self) -> None:
        """Request stop listening.

        This stops all servers and thus they no longer accept a new connections but the
        old connections are still kept and working.
        """
        for server in self.servers.values():
            server.close()

    async def wait_closed(self) -> None:
        """Wait for close to complete."""
        await asyncio.gather(
            *(server.wait_closed() for server in self.servers.values()),
            return_exceptions=True,
        )

    async def terminate(self) -> None:
        """Request termination of the broker.

        This closes broker as well as disconnects all established clients.
        """
        self.close()
        await self.wait_closed()
        await asyncio.gather(*(client.disconnect() for client in self.clients.values()))

    class Client(SimpleClient):
        """Single client connected to the broker."""

        APP_NAME = "pyshvbroker"
        try:
            APP_VERSION = importlib.metadata.version("pyshv")
        except importlib.metadata.PackageNotFoundError:
            APP_VERSION = "unknown"

        class State(enum.Enum):
            """State of the client."""

            CONNECTED = enum.auto()
            HELLO = enum.auto()
            LOGIN = enum.auto()

        def __init__(
            self,
            client: RpcClient,
            broker: "RpcBroker",
            broker_client_id: int,
        ):
            super().__init__(client)
            self.subscriptions: set[RpcSubscription] = set()
            """Set of all subscriptions."""
            self.state = self.State.CONNECTED
            """Specifies state of the client login process."""
            self.user: RpcBrokerConfig.User | None = None
            """User used to login to the broker."""
            self._nonce = "".join(random.choice("0123456789abcdef") for _ in range(8))
            self.__broker = broker
            self.__broker_client_id = broker_client_id
            self.__mount_point: str | None = None

        @property
        def broker(self) -> "RpcBroker":
            """Broker this client is part of."""
            return self.__broker

        @property
        def broker_client_id(self) -> int:
            """Identifier assigned to the client in the broker."""
            return self.__broker_client_id

        @property
        def mount_point(self) -> str | None:
            """Mount point of this client, if any."""
            return self.__mount_point

        def _lschng_path(self, path: str) -> tuple[str, str]:
            pth = path.split("/")
            valid_level = 0
            for c in self.__broker.clients.values():
                if c.mount_point is None or c.mount_point == path:
                    continue
                valid_level = max(
                    valid_level,
                    sum(
                        1
                        for _ in itertools.takewhile(
                            lambda v: v[0] == v[1], zip(pth, c.mount_point.split("/"))
                        )
                    ),
                )
            return "/".join(pth[:valid_level]), pth[valid_level]

        async def set_mount_point(self, value: str | None) -> None:
            if value is not None:
                # We remove trailing slash because otherwise we could fail when we
                # compare this string against path of exactly this node.
                value = value.rstrip("/")
            if self.__mount_point == value:
                return
            lschng: RpcMessage | None = None
            if self.__mount_point is not None:
                path, node = self._lschng_path(self.__mount_point)
                lschng = RpcMessage.signal(
                    path, "lschng", {node: False}, RpcMethodAccess.BROWSE
                )
            self.__mount_point = value
            if value is not None:
                path, node = self._lschng_path(value)
                if lschng is not None and lschng.path == path:
                    lschng.param[node] = True  # type: ignore
                else:
                    if lschng is not None:
                        await self.__broker.signal(lschng)
                    lschng = RpcMessage.signal(
                        path, "lschng", {node: True}, RpcMethodAccess.BROWSE
                    )
            if lschng is not None:
                await self.__broker.signal(lschng)
            if value:
                logger.info(
                    "Client with ID %d is now mounted on: %s",
                    self.__broker_client_id,
                    value,
                )

        async def _loop(self) -> None:
            await super()._loop()
            self.__broker.clients.pop(self.__broker_client_id, None)
            if self.__mount_point is not None:
                path, node = self._lschng_path(self.__mount_point)
                await self.__broker.signal(
                    RpcMessage.signal(
                        path, "lschng", {node: False}, RpcMethodAccess.BROWSE
                    )
                )
            self.client.disconnect()
            await self.client.wait_disconnect()
            logger.info("Client disconnected: %s", self.__broker_client_id)

        async def _activity_loop(self) -> None:
            """Loop run alongside with :meth:`_loop` to disconnect inactive clients."""
            while self.client.connected:
                t = time.monotonic() - self.client.last_receive
                if t < self.IDLE_TIMEOUT:
                    await asyncio.sleep(self.IDLE_TIMEOUT - t)
                else:
                    await self.disconnect()

        async def _message(self, msg: RpcMessage) -> None:
            if self.state == self.State.CONNECTED:
                return await self.client.send(await self._message_hello(msg))
            if self.state == self.State.HELLO:
                return await self.client.send(await self._message_login(msg))

            if msg.is_request:
                # Set access granted to the level allowed by user
                assert self.user is not None
                access = self.user.access_level(msg.path, msg.method)
                if access is None:
                    resp = msg.make_response()
                    resp.rpc_error = RpcError(
                        "No access", RpcErrorCode.METHOD_NOT_FOUND
                    )
                    await self.client.send(resp)
                    return
                if access is not RpcMethodAccess.ADMIN or msg.rpc_access is None:
                    msg.rpc_access = access
                # Check if we should delegate it or handle it ourself
                if (cpath := self.__broker.client_on_path(msg.path)) is None:
                    return await super()._message(msg)
                # Propagate to some peer
                msg.caller_ids = list(msg.caller_ids) + [self.__broker_client_id]
                msg.path = cpath[1]
                await cpath[0].client.send(msg)

            if msg.is_response:
                cids = list(msg.caller_ids)
                if not cids:  # no caller IDs means this is message for us
                    return await super()._message(msg)
                cid = cids.pop()
                msg.caller_ids = cids
                try:
                    peer = self.__broker.clients[cid]
                except KeyError:
                    return
                await peer.client.send(msg)

            if msg.is_signal and self.mount_point is not None:
                msg.path = self.mount_point + "/" + msg.path
                await self.__broker.signal(msg)

        async def _message_hello(self, msg: RpcMessage) -> RpcMessage:
            resp = msg.make_response()
            if msg.is_request and msg.method == "hello":
                self.state = self.State.HELLO
                resp = msg.make_response()
                resp.result = {"nonce": self._nonce}
            else:
                resp.rpc_error = RpcError(
                    "Only 'hello' is allowed", RpcErrorCode.INVALID_REQUEST
                )
            return resp

        async def _message_login(self, msg: RpcMessage) -> RpcMessage:
            resp = msg.make_response()
            if not msg.is_request or msg.method != "login":
                resp.rpc_error = RpcError(
                    "Only 'login' is allowed", RpcErrorCode.INVALID_REQUEST
                )
                return resp
            param = msg.param
            resp = msg.make_response()
            if isinstance(param, collections.abc.Mapping):
                self.user = self.broker.config.login(
                    shvget(param, ("login", "user"), str, ""),
                    shvget(param, ("login", "password"), str, ""),
                    self._nonce,
                    RpcLoginType(
                        shvget(param, ("login", "type"), str, RpcLoginType.SHA1.value)
                    ),
                )
                if self.user is None:
                    resp.rpc_error = RpcError(
                        "Invalid login", RpcErrorCode.METHOD_CALL_EXCEPTION
                    )
                    return resp
                mount_point = shvget(
                    param, ("options", "device", "mountPoint"), str, ""
                )
                if self.broker.client_on_path(mount_point) is not None:
                    resp.rpc_error = RpcError(
                        "Mount point already mounted",
                        RpcErrorCode.METHOD_CALL_EXCEPTION,
                    )
                    return resp
                if mount_point:
                    await self.set_mount_point(mount_point)
                self.IDLE_TIMEOUT = float(
                    shvget(
                        param,
                        ("options", "idleWatchDogTimeOut"),
                        int,
                        self.IDLE_TIMEOUT,
                    )
                )
                resp.result = {"clientId": self.broker_client_id}
                self.state = self.State.LOGIN
            else:
                resp.rpc_error = RpcError(
                    "Invalid type of parameters", RpcErrorCode.INVALID_PARAMS
                )
            return resp

        def _ls(self, path: str) -> typing.Iterator[str]:
            yield from super()._ls(path)
            if path == ".app":
                yield "broker"
            elif path == ".app/broker":
                yield "currentClient"
                yield "client"
                yield "clientInfo"
            elif path in (".app/broker/clientInfo", ".app/broker/client"):
                yield from map(str, self.broker.clients.keys())
            else:
                for client in self.broker.clients.values():
                    mnt = client.mount_point
                    if mnt is not None:
                        if path == "":
                            yield mnt.split("/", maxsplit=1)[0]
                        elif mnt.startswith(path + "/"):
                            yield mnt[len(path) + 1 :].split("/", maxsplit=1)[0]

        def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
            yield from super()._dir(path)
            if path == ".app/broker":
                yield RpcMethodDesc("clientInfo", access=RpcMethodAccess.SERVICE)
                yield RpcMethodDesc.getter("clients", access=RpcMethodAccess.SERVICE)
                yield RpcMethodDesc("disconnectClient", access=RpcMethodAccess.SERVICE)
                yield RpcMethodDesc.getter("mountPoints")
            elif path == ".app/broker/currentClient":
                yield RpcMethodDesc.getter("info", access=RpcMethodAccess.BROWSE)
                yield RpcMethodDesc("subscribe", access=RpcMethodAccess.READ)
                yield RpcMethodDesc("unsubscribe", access=RpcMethodAccess.READ)
                yield RpcMethodDesc("rejectNotSubscribed", access=RpcMethodAccess.READ)
                yield RpcMethodDesc.getter("subscriptions")
            elif (
                path.startswith(".app/broker/clientInfo/")
                and self.broker.get_client(path[23:]) is not None
            ):
                yield RpcMethodDesc.getter("userName", "String")
                yield RpcMethodDesc.getter("mountPoint", "String")
                yield RpcMethodDesc.getter("subscriptions")
                yield RpcMethodDesc("dropClient", access=RpcMethodAccess.SERVICE)
                yield RpcMethodDesc.getter("idleTime")
                yield RpcMethodDesc.getter("idleTimeMax")

        async def _method_call(
            self, path: str, method: str, access: RpcMethodAccess, param: SHVType
        ) -> SHVType:
            if path == ".app/broker":
                if method == "clientInfo" and access >= RpcMethodAccess.SERVICE:
                    if not isinstance(param, int):
                        raise RpcInvalidParamsError("Use Int")
                    client = self.broker.get_client(param)
                    return client.infomap() if client is not None else None
                if method == "mountedClientInfo" and access >= RpcMethodAccess.SERVICE:
                    if not isinstance(param, str):
                        raise RpcInvalidParamsError("Use String with SHV path")
                    client_pth = self.broker.client_on_path(param)
                    if client_pth is not None:
                        return client_pth[0].infomap()
                    return None
                if method == "clients" and access >= RpcMethodAccess.SERVICE:
                    return list(self.broker.clients.keys())
                if method == "disconnectClient" and access >= RpcMethodAccess.SERVICE:
                    if not isinstance(param, int):
                        raise RpcInvalidParamsError("Use Int")
                    client = self.broker.get_client(param)
                    if client is None:
                        raise RpcMethodCallExceptionError(
                            f"No such client with ID: {param}"
                        )
                    await client.disconnect()
                    return None
                if method == "mountPoints" and access >= RpcMethodAccess.READ:
                    return [
                        "/".join(c.mount_point)
                        for c in self.broker.clients.values()
                        if c.mount_point
                    ]
            elif path == ".app/broker/currentClient":
                if method == "info":
                    return self.infomap()
                if access >= RpcMethodAccess.READ:
                    if method == "subscriptions":
                        return self.subslist()
                    if method == "subscribe":
                        assert self.user is not None
                        sub = RpcSubscription.fromSHV(param)
                        self.subscriptions.add(sub)
                        # TODO support subscription to the subbroker
                        return None
                    if method == "unsubscribe":
                        sub = RpcSubscription.fromSHV(param)
                        try:
                            self.subscriptions.remove(sub)
                        except KeyError:
                            return False
                        # TODO we should also scan subbrokers and drop any subscribe
                        # that no longer matches some of ours because
                        # rejectNotSubscribed doesn't work for invalid paths.
                        return True
                    if method == "rejectNotSubscribed":
                        method = shvget(param, "method", str, "chng")
                        path = shvget(param, "path", str, "")
                        match = {
                            sub
                            for sub in self.subscriptions
                            if sub.applies(path, method)
                        }
                        self.subscriptions -= match
                        return [
                            {"method": sub.method, "path": sub.path} for sub in match
                        ]
            elif (
                path.startswith(".app/broker/clientInfo/")
                and (client := self.broker.get_client(path[23:])) is not None
                and access >= RpcMethodAccess.SERVICE
            ):
                if method == "userName":
                    assert client.user is not None
                    return client.user.name
                if method == "mountPoint":
                    return "/".join(self.mount_point) if self.mount_point else None
                if method == "subscriptions":
                    return client.subslist()
                if method == "dropClient":
                    await client.disconnect()
                    return None
                if method == "idleTime":
                    return int((time.monotonic() - client.client.last_receive) * 1000)
                if method == "idleTimeMax":
                    return int(self.IDLE_TIMEOUT * 1000)
            return await super()._method_call(path, method, access, param)

        def infomap(self) -> SHVType:
            """Produce Map with client's info.

            This is primarilly used internally by SVH Broker. You most likely won't have
            use for it outside of SHV Broker context.
            """
            return {
                "clientId": self.broker_client_id,
                "userName": getattr(self.user, "name", None),
                "mountPoint": self.mount_point,
                "subscriptions": self.subslist(),
            }

        def subslist(self) -> SHVType:
            """Produce List of all client's subscriptions.

            This is primarilly used internally by SVH Broker. You most likely won't have
            use for it outside of SHV Broker context.
            """
            return [{"method": s.method, "path": s.path} for s in self.subscriptions]

        async def disconnect(self) -> None:
            logger.info("Disconnecting client: %d", self.broker_client_id)
            self.broker.clients.pop(self.broker_client_id, None)
            await super().disconnect()
