"""Common state for the RPC broker that works as server in the SHV network."""
from __future__ import annotations

import asyncio
import collections.abc
import importlib.metadata
import itertools
import logging
import random
import time
import typing

from .. import VERSION
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

    class Client(SimpleClient):
        """Single client connected to the broker."""

        APP_NAME = "pyshvbroker"
        """Name reported as application name for pySHVBroker."""
        APP_VERSION = VERSION
        """pySHVBroker version."""

        IDLE_TIMEOUT_LOGIN: float = 5
        """:param:`IDLE_TIMEOUT` set for clients without user.

        This is intentionally shorter to quickly disconnect inactive clients
        that are not participating in SHV RPC.
        """

        def __init__(
            self,
            client: RpcClient,
            broker: RpcBroker,
            user: RpcBrokerConfig.User | None = None,
            **kwargs: typing.Any,
        ):
            super().__init__(client, **kwargs)
            self.idle_disconnect = True
            self.subscriptions: set[RpcSubscription] = set()
            """Set of all subscriptions."""
            self.user = user
            """User used to login to the broker."""
            if user is not None:
                self.IDLE_TIMEOUT = self.IDLE_TIMEOUT_LOGIN
            self._nonce: str | None = None
            self.__broker = broker
            self.__broker_client_id = broker.next_caller_id()
            self.__mount_point: str | None = None
            self.__peer_is_broker: bool | None = None
            self.__maintain_subscriptions_lock = asyncio.Lock()
            broker.clients[self.__broker_client_id] = self
            logger.info(
                "Client registered to broker with ID %d", self.__broker_client_id
            )

        @property
        def broker(self) -> RpcBroker:
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
            # Prepare lschng signal with old path
            lschng: RpcMessage | None = None
            if self.__mount_point is not None:
                path, node = self._lschng_path(self.__mount_point)
                lschng = RpcMessage.signal(
                    path, "lschng", {node: False}, RpcMethodAccess.BROWSE
                )
            was_mounted = self.__mount_point is not None
            # Perform mount point change
            self.__mount_point = value
            if value is not None:
                # Prepare lschng for new path. We need to tackle here root change and
                # thus we might need to send it first before we generate the one with
                # correct root.
                path, node = self._lschng_path(value)
                if lschng is not None and lschng.path == path:
                    lschng.param[node] = True  # type: ignore
                else:
                    if lschng is not None:
                        await self.__broker.signal(lschng)
                    lschng = RpcMessage.signal(
                        path, "lschng", {node: True}, RpcMethodAccess.BROWSE
                    )
            # Send lschng signal
            assert lschng is not None
            await self.__broker.signal(lschng)
            # Now remove old subscriptions and add new ones
            await self.maintain_subscriptions(cleanup=was_mounted)
            if value:
                logger.info(
                    "Client with ID %d is now mounted on: %s",
                    self.__broker_client_id,
                    value,
                )

        async def peer_is_broker(self) -> bool:
            """Identify if peer this client is handle for is broker."""
            if self.__peer_is_broker is None:
                try:
                    lsr = await self.call(".app", "ls", "broker")
                    self.__peer_is_broker = lsr if isinstance(lsr, bool) else False
                except RpcError:
                    self.__peer_is_broker = False
            return self.__peer_is_broker

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
            logger.info("Client with ID %d disconnected", self.__broker_client_id)

        async def _message(self, msg: RpcMessage) -> None:
            if self.user is None:
                if self._nonce is None:
                    return await self.client.send(self._message_hello(msg))
                return await self.client.send(self._message_login(msg))

            if msg.is_request:
                # Set access granted to the level allowed by user
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

        def _message_hello(self, msg: RpcMessage) -> RpcMessage:
            resp = msg.make_response()
            if msg.is_request and msg.method == "hello":
                self._nonce = "".join(
                    random.choice("0123456789abcdef") for _ in range(8)
                )
                resp = msg.make_response()
                resp.result = {"nonce": self._nonce}
            else:
                resp.rpc_error = RpcError(
                    "Only 'hello' is allowed", RpcErrorCode.INVALID_REQUEST
                )
            return resp

        def _message_login(self, msg: RpcMessage) -> RpcMessage:
            assert self._nonce is not None
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
                logger.info(
                    "Client with ID %d logged in as user: %s",
                    self.__broker_client_id,
                    self.user.name,
                )
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
                    asyncio.create_task(self.set_mount_point(mount_point))
                self.IDLE_TIMEOUT = float(
                    shvget(
                        param,
                        ("options", "idleWatchDogTimeOut"),
                        int,
                        type(self).IDLE_TIMEOUT,
                    )
                )
                resp.result = {"clientId": self.broker_client_id}
            else:
                resp.rpc_error = RpcError(
                    "Invalid type of parameters", RpcErrorCode.INVALID_PARAMS
                )
            return resp

        def _ls(self, path: str) -> typing.Iterator[str]:
            yield from super()._ls(path)
            match path:
                case ".app":
                    yield "broker"
                case ".app/broker":
                    yield "currentClient"
                    yield "client"
                    yield "clientInfo"
                case ".app/broker/clientInfo" | ".app/broker/client":
                    yield from map(str, self.broker.clients.keys())
                case _:
                    for client in self.broker.clients.values():
                        mnt = client.mount_point
                        if mnt is not None:
                            if path == "":
                                yield mnt.split("/", maxsplit=1)[0]
                            elif mnt.startswith(path + "/"):
                                yield mnt[len(path) + 1 :].split("/", maxsplit=1)[0]

        def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
            yield from super()._dir(path)
            match path:
                case ".app/broker":
                    yield RpcMethodDesc(
                        "clientInfo", access=RpcMethodAccess.SUPER_SERVICE
                    )
                    yield RpcMethodDesc(
                        "mountedClientInfo", access=RpcMethodAccess.SUPER_SERVICE
                    )
                    yield RpcMethodDesc.getter(
                        "clients", access=RpcMethodAccess.SUPER_SERVICE
                    )
                    yield RpcMethodDesc.getter(
                        "mounts", access=RpcMethodAccess.SUPER_SERVICE
                    )
                    yield RpcMethodDesc(
                        "disconnectClient", access=RpcMethodAccess.SUPER_SERVICE
                    )
                case ".app/broker/currentClient":
                    yield RpcMethodDesc.getter("info", access=RpcMethodAccess.BROWSE)
                    yield RpcMethodDesc("subscribe", access=RpcMethodAccess.BROWSE)
                    yield RpcMethodDesc("unsubscribe", access=RpcMethodAccess.BROWSE)
                    yield RpcMethodDesc(
                        "rejectNotSubscribed", access=RpcMethodAccess.BROWSE
                    )
                    yield RpcMethodDesc.getter(
                        "subscriptions", access=RpcMethodAccess.BROWSE
                    )
                case _ if (
                    path.startswith(".app/broker/clientInfo/")
                    and self.broker.get_client(path[23:]) is not None
                ):
                    yield RpcMethodDesc.getter("userName", "String")
                    yield RpcMethodDesc.getter("mountPoint", "String")
                    yield RpcMethodDesc.getter("subscriptions")
                    yield RpcMethodDesc(
                        "dropClient", access=RpcMethodAccess.SUPER_SERVICE
                    )
                    yield RpcMethodDesc.getter("idleTime")
                    yield RpcMethodDesc.getter("idleTimeMax")

        async def _method_call(
            self, path: str, method: str, access: RpcMethodAccess, param: SHVType
        ) -> SHVType:
            assert self.user is not None  # Otherwise handled in _message
            if path == ".app/broker" and access >= RpcMethodAccess.SUPER_SERVICE:
                match method:
                    case "clientInfo":
                        if not isinstance(param, int):
                            raise RpcInvalidParamsError("Use Int")
                        client = self.broker.get_client(param)
                        return client.infomap() if client is not None else None
                    case "mountedClientInfo":
                        if not isinstance(param, str):
                            raise RpcInvalidParamsError("Use String with SHV path")
                        client_pth = self.broker.client_on_path(param)
                        if client_pth is not None:
                            return client_pth[0].infomap()
                        return None
                    case "clients":
                        return list(self.broker.clients.keys())
                    case "mounts":
                        return [
                            "/".join(c.mount_point)
                            for c in self.broker.clients.values()
                            if c.mount_point
                        ]
                    case "disconnectClient":
                        if not isinstance(param, int):
                            raise RpcInvalidParamsError("Use Int")
                        client = self.broker.get_client(param)
                        if client is None:
                            raise RpcMethodCallExceptionError(
                                f"No such client with ID: {param}"
                            )
                        await client.disconnect()
                        return None
            elif path == ".app/broker/currentClient":
                match method:
                    case "info":
                        return self.infomap()
                    case "subscriptions":
                        return self.subslist()
                    case "subscribe":
                        sub = RpcSubscription.fromSHV(param)
                        self.subscriptions.add(sub)
                        async for subb in self.broker.subbrokers():
                            assert subb.mount_point is not None
                            if self.user.could_receive_signal(sub, subb.mount_point):
                                if subsub := sub.relative_to(subb.mount_point):
                                    await subb.subscribe(subsub)
                        return None
                    case "unsubscribe":
                        sub = RpcSubscription.fromSHV(param)
                        try:
                            self.subscriptions.remove(sub)
                        except KeyError:
                            return False
                        async for subb in self.broker.subbrokers():
                            await subb.maintain_subscriptions()
                        return True
                    case "rejectNotSubscribed":
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
                and access >= RpcMethodAccess.SUPER_SERVICE
            ):
                match method:
                    case "userName":
                        return client.user.name if client.user is not None else None
                    case "mountPoint":
                        return "/".join(self.mount_point) if self.mount_point else None
                    case "subscriptions":
                        return client.subslist()
                    case "dropClient":
                        await client.disconnect()
                        return None
                    case "idleTime":
                        return int(
                            (time.monotonic() - client.client.last_receive) * 1000
                        )
                    case "idleTimeMax":
                        return int(self.IDLE_TIMEOUT * 1000)
            return await super()._method_call(path, method, access, param)

        def infomap(self) -> SHVType:
            """Produce Map with client's info.

            This is primarilly used internally by SVH Broker. You most likely won't have
            use for it outside of SHV Broker context.
            """
            return {
                "clientId": self.broker_client_id,
                "userName": self.user.name if self.user is not None else None,
                "mountPoint": self.mount_point,
                "subscriptions": self.subslist(),
            }

        def subslist(self) -> SHVType:
            """Produce List of all client's subscriptions.

            This is primarilly used internally by SVH Broker. You most likely won't have
            use for it outside of SHV Broker context.
            """
            return [{"method": s.method, "path": s.path} for s in self.subscriptions]

        async def maintain_subscriptions(self, cleanup: bool = True) -> None:
            """Remove no longer valid subscriptions and add missing ones.

            This does nothing if peer of this client is not sub-broker.

            :param cleanup: If cleanup should be performed or if it is enough to
            just push all subscriptions.
            """
            assert self.user is not None
            if not await self.peer_is_broker():
                return
            # We lock here because we do multiple calls and we must be sure that nobody
            # is going to be doing the same as us.
            async with self.__maintain_subscriptions_lock:
                present: set[RpcSubscription] = set()
                required: set[RpcSubscription] = set()
                if cleanup:
                    rsubs = await self.call(
                        ".app/broker/currentClient", "subscriptions"
                    )
                    # TODO error instead of assert
                    assert isinstance(rsubs, collections.abc.Sequence)
                    present = {RpcSubscription.fromSHV(sub) for sub in rsubs}
                if self.mount_point is not None:
                    for client in self.broker.clients.values():
                        if client.user is None:
                            continue
                        for sub in client.subscriptions:
                            if client.user.could_receive_signal(sub, self.mount_point):
                                if subsub := sub.relative_to(self.mount_point):
                                    required.add(subsub)
                for sub in present - required:
                    await self.unsubscribe(sub)
                for sub in required - present:
                    await self.subscribe(sub)

        async def disconnect(self) -> None:
            logger.info("Disconnecting client with ID %d", self.broker_client_id)
            self.broker.clients.pop(self.broker_client_id, None)
            await super().disconnect()

    def __init__(self, config: RpcBrokerConfig) -> None:
        self.clients: dict[int, RpcBroker.Client] = {}
        """Mapping from client IDs to client objects."""
        self.config = config
        """Configuration of the RPC Broker."""
        self.servers: dict[str, RpcServer] = {}
        """All servers managed by Broker where keys are their configured names."""
        self.__connection_tasks: dict[str, asyncio.Task] = {}
        self.__next_caller_id = 0

    def next_caller_id(self) -> int:
        """Allocate new caller ID."""
        # TODO try to reuse older caller IDs to send smaller messages but we need to do
        # it only after some given delay. We can safe time of client disconnect to the
        # self.clients and use that to identify when we can reuse caller id.
        self.__next_caller_id += 1
        return self.__next_caller_id - 1

    def add_client(
        self,
        client: RpcClient,
        user: RpcBrokerConfig.User | None = None,
    ) -> Client:
        """Add a new client to be handled by the broker.

        :param client: RPC client instance to be handled by broker.
        :param user: The user this client is logged in. Use ``None`` if you
          require login from this client.
        :return: The client instance in the broker.
        """
        return self.Client(client, self, user, idle_disconnect=True)

    def get_client(self, cid: int | str) -> typing.Union[Client, None]:
        """Lookup client with given ID.

        :param cid: ID of the client either as string or as integer.
        :return: :class:`RpcBroker.Client` when such client is located and ``None``
            otherwise.
        """
        try:
            return self.clients[cid if isinstance(cid, int) else int(cid, 10)]
        except (ValueError, KeyError):
            return None

    def client_on_path(self, path: str) -> tuple[Client, str] | None:
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

    async def subbrokers(self) -> collections.abc.AsyncIterator[Client]:
        """Iterate over all mounted clients that are brokers."""
        for client in self.clients.values():
            if client.user is None:
                continue  # Ignore unlogged clients
            if client.mount_point is not None and await client.peer_is_broker():
                yield client

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

    async def start_serving(self) -> None:
        """Start accepting connectons on all configured servers."""

        def add(client: RpcClient) -> None:
            self.add_client(client)

        for name, url in self.config.listen.items():
            if name not in self.servers:
                self.servers[name] = await create_rpc_server(add, url)
        for connection in self.config.connections():
            if connection.name not in self.__connection_tasks:
                self.__connection_tasks[connection.name] = asyncio.create_task(
                    self._connection_task(connection)
                )

    async def _connection_task(self, connection: RpcBrokerConfig.Connection) -> None:
        """Loop that connects client."""
        timeout = 1
        while True:
            client = None
            try:
                client = await self.Client.connect(
                    connection.url, self, connection.user
                )
                await client.client.wait_disconnect()
            except Exception as exc:
                logger.error(
                    "Client connection '%s' failure (waiting %d secs): %s",
                    connection.name,
                    timeout,
                    exc.message if isinstance(exc, RpcError) else exc,
                )
                await asyncio.sleep(timeout)
                timeout = (timeout * 2) % 512
            else:
                timeout = 1
            finally:
                if client is not None:
                    await client.disconnect()

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
        for connection in self.__connection_tasks.values():
            connection.cancel()
            try:
                await connection
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.error("Connection task failure: %s", exc)
        await self.wait_closed()
        await asyncio.gather(*(client.disconnect() for client in self.clients.values()))
