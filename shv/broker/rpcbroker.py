"""Common state for the RPC broker that works as server in the SHV network."""
from __future__ import annotations

import asyncio
import collections.abc
import contextlib
import logging
import random
import string
import time
import typing

from ..__version__ import __version__
from ..rpcclient import RpcClient, init_rpc_client
from ..rpcerrors import (
    RpcError,
    RpcErrorCode,
    RpcInvalidParamsError,
    RpcLoginRequiredError,
    RpcMethodCallExceptionError,
)
from ..rpcmessage import RpcMessage
from ..rpcmethod import RpcMethodAccess, RpcMethodDesc
from ..rpcserver import RpcServer, create_rpc_server
from ..rpcsubscription import RpcSubscription
from ..rpcurl import RpcLoginType
from ..simplebase import SimpleBase
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

    class Client(SimpleBase):
        """Single client connected to the broker."""

        APP_NAME = "pyshvbroker"
        """Name reported as application name for pySHVBroker."""
        APP_VERSION = __version__
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
            *args: typing.Any,
            user: RpcBrokerConfig.User | None = None,
            **kwargs: typing.Any,
        ):
            super().__init__(client, *args, **kwargs)
            self.subs: set[RpcSubscription] = set()
            """Set of all subscriptions client requested."""
            self.user: RpcBrokerConfig.User | None = user
            """Local user used to deduce access rights."""
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

        @property
        def active(self) -> bool:
            """Check if given client is actively communicating.

            Client can be inactive for example due to being disconnected, or in
            the middle of reset, or waiting for login.
            """
            return self.user is not None and self.client.connected

        async def set_mount_point(self, value: str | None) -> None:
            if value is not None:
                # We remove trailing slash because otherwise we could fail when we
                # compare this string against path of exactly this node.
                value = value.rstrip("/")
            changes = [m for m in (self.__mount_point, value) if m is not None]
            self.__mount_point = value
            await self.__broker.signal_mount_point_change(*changes)
            if value:
                logger.info(
                    "Client with ID %d is now mounted on: %s",
                    self.__broker_client_id,
                    value,
                )

        async def peer_is_broker(self) -> bool:
            """Identify if peer this client is handle for is broker."""
            if self.__peer_is_broker is None:
                self.__peer_is_broker = False
                with contextlib.suppress(RpcError):
                    lsr = await self.call(".app", "ls", "broker")
                    self.__peer_is_broker = lsr if isinstance(lsr, bool) else False
            return self.__peer_is_broker

        async def _message(self, msg: RpcMessage) -> None:
            assert self.user is not None
            if msg.is_request:
                # Set access granted to the level allowed by user
                access = self.user.access_level(msg.path, msg.method)
                if access is None:
                    return await self.client.send(
                        msg.make_response(
                            error=RpcError("No access", RpcErrorCode.METHOD_NOT_FOUND)
                        )
                    )
                msg.rpc_access = (
                    access
                    if msg.rpc_access is None or msg.rpc_access > access
                    else msg.rpc_access
                )
                # Check if we should delegate it or handle it ourself
                if (cpath := self.__broker.client_on_path(msg.path)) is None:
                    return await super()._message(msg)
                # Propagate to some peer
                msg.caller_ids = [*msg.caller_ids, self.__broker_client_id]
                msg.path = cpath[1]
                await cpath[0].send(msg)

            elif msg.is_response:
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

            elif msg.is_signal and self.mount_point is not None:
                msg.path = self.mount_point + "/" + msg.path
                await self.__broker.signal(msg)

        def _reset(self) -> None:
            self.subs = set()
            self.__broker.clients.pop(self.__broker_client_id, None)
            self.__broker_client_id = self.__broker.next_caller_id()
            self.__broker.clients[self.__broker_client_id] = self
            self.__peer_is_broker = None
            asyncio.create_task(self.set_mount_point(None))

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
                        return [s.toSHV() for s in self.subs]
                    case "subscribe":
                        sub = RpcSubscription.fromSHV(param)
                        self.subs.add(sub)
                        async for subb in self.broker.subbrokers():
                            assert subb.mount_point is not None
                            if self.user.could_receive_signal(sub, subb.mount_point):
                                if subsub := sub.relative_to(subb.mount_point):
                                    await subb.call(
                                        ".app/broker/currentClient"
                                        if await self._peer_is_shv3()
                                        else ".broker/app",
                                        "subscribe",
                                        subsub.toSHV(),
                                    )
                        return None
                    case "unsubscribe":
                        sub = RpcSubscription.fromSHV(param)
                        try:
                            self.subs.remove(sub)
                        except KeyError:
                            return False
                        async for subb in self.broker.subbrokers():
                            await subb.maintain_subscriptions()
                        return True
                    case "rejectNotSubscribed":
                        method = shvget(param, "method", str, "chng")
                        path = shvget(param, "path", str, "")
                        match = {sub for sub in self.subs if sub.applies(path, method)}
                        self.subs -= match
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
                        return [s.toSHV() for s in self.subs]
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

            This is info provided to administator to inform it about this
            client.
            """
            return {
                "clientId": self.broker_client_id,
                "userName": self.user.name if self.user is not None else None,
                "mountPoint": self.mount_point,
                "subscriptions": [s.toSHV() for s in self.subs],
            }

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
                        for sub in client.subs:
                            if client.user.could_receive_signal(sub, self.mount_point):
                                if subsub := sub.relative_to(self.mount_point):
                                    required.add(subsub)
                for sub in present - required:
                    await self.call(
                        ".app/broker/currentClient"
                        if await self._peer_is_shv3()
                        else ".broker/app",
                        "unsubscribe",
                        sub.toSHV(),
                    )
                for sub in required - present:
                    await self.call(
                        ".app/broker/currentClient"
                        if await self._peer_is_shv3()
                        else ".broker/app",
                        "subscribe",
                        sub.toSHV(),
                    )

        async def disconnect(self) -> None:
            logger.info("Disconnecting client with ID %d", self.broker_client_id)
            self.broker.clients.pop(self.broker_client_id, None)
            await super().disconnect()

    class LoginClient(Client):
        """Broker's client that expects login from client."""

        def __init__(self, *args: typing.Any, **kwargs: typing.Any):
            super().__init__(*args, **kwargs)
            self.IDLE_TIMEOUT = self.IDLE_TIMEOUT_LOGIN
            self._nonce: str = ""

        async def _loop(self) -> None:
            activity_task = asyncio.create_task(self._activity_loop())
            await super()._loop()
            activity_task.cancel()
            with contextlib.suppress(asyncio.exceptions.CancelledError):
                await activity_task

            self.broker.clients.pop(self.broker_client_id, None)
            await self.set_mount_point(None)
            self.client.disconnect()
            await self.client.wait_disconnect()
            logger.info("Client with ID %d disconnected", self.broker_client_id)

        async def _activity_loop(self) -> None:
            """Loop run alongside with :meth:`_loop`.

            It disconnects this client if it is idling.
            """
            while self.client.connected:
                t = time.monotonic() - self.client.last_receive
                if t < self.IDLE_TIMEOUT:
                    await asyncio.sleep(self.IDLE_TIMEOUT - t)
                else:
                    await self.disconnect()

        async def _message(self, msg: RpcMessage) -> None:
            if self.user is None:
                if msg.is_request:
                    await self.client.send(self._message_login(msg))
                return
            await super()._message(msg)

        def _message_login(self, msg: RpcMessage) -> RpcMessage:
            if not msg.path:
                if msg.method == "hello":
                    self._nonce = "".join(random.choices(string.hexdigits, k=10))
                    return msg.make_response({"nonce": self._nonce})
                if self._nonce and msg.method == "login":
                    param = msg.param
                    if not isinstance(param, collections.abc.Mapping):
                        return msg.make_response(
                            error=RpcInvalidParamsError("Invalid type of parameters")
                        )
                    self.user = self.broker.config.login(
                        shvget(param, ("login", "user"), str, ""),
                        shvget(param, ("login", "password"), str, ""),
                        self._nonce,
                        RpcLoginType(
                            shvget(
                                param, ("login", "type"), str, RpcLoginType.SHA1.value
                            )
                        ),
                    )
                    if self.user is None:
                        return msg.make_response(
                            error=RpcMethodCallExceptionError("Invalid login")
                        )
                    logger.info(
                        "Client with ID %d logged in as user: %s",
                        self.broker_client_id,
                        self.user.name,
                    )
                    mount_point = shvget(
                        param, ("options", "device", "mountPoint"), str, ""
                    )
                    if self.broker.client_on_path(mount_point) is not None:
                        return msg.make_response(
                            error=RpcError(
                                "Mount point already mounted",
                                RpcErrorCode.METHOD_CALL_EXCEPTION,
                            )
                        )
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
                    return msg.make_response({"clientId": self.broker_client_id})
            return msg.make_response(
                error=RpcLoginRequiredError(
                    "Use hello and login methods" if self._nonce else "Use hello method"
                )
            )

        def _reset(self) -> None:
            self._nonce = ""
            self.user = None
            super()._reset()

    class ConnectClient(SimpleClient, Client):
        """Broker client that activelly connects to some other peer."""

        def __init__(
            self,
            *args: typing.Any,
            target_mount_point: str | None = None,
            **kwargs: typing.Any,
        ):
            super().__init__(*args, **kwargs)
            self.target_mount_point = target_mount_point

        async def _login(self) -> None:
            await super()._login()
            await self.set_mount_point(self.target_mount_point)

        # TODO possibly add info about where it is connect to the infomap

    def __init__(self, config: RpcBrokerConfig) -> None:
        self.clients: dict[int, RpcBroker.Client] = {}
        """Mapping from client IDs to client objects."""
        self.config = config
        """Configuration of the RPC Broker."""
        self.servers: dict[str, RpcServer] = {}
        """All servers managed by Broker where keys are their configured names."""
        self.__last_caller_id = -1

    def next_caller_id(self) -> int:
        """Allocate new caller ID."""
        # TODO try to reuse older caller IDs to send smaller messages but we
        # need to do it only after some given delay. We can safe time of client
        # disconnect to the self.clients and use that to identify when we can
        # reuse caller id.
        self.__last_caller_id += 1
        return self.__last_caller_id

    def get_client(self, cid: int | str) -> Client | None:
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

    def mounted_clients(self) -> collections.abc.Iterator[Client]:
        """Goes through all active clients and provides those mounted."""
        return (
            c for c in self.clients.values() if c.active and c.mount_point is not None
        )

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
                and any(s.applies(msg.path, msg.method) for s in client.subs)
            ):
                await client.client.send(msg)

    async def signal_mount_point_change(self, *path: str) -> None:
        """Send lschng signal for node changes for given mount points.

        The state of the mount point can be deduced from the current list of
        them.

        You most likely do not want to call this if you are just a Broker user.
        It is used by broker's clients to inform all peers about mount point
        changes. Think about before you use this in your application!
        """
        mounts = set(c.mount_point for c in self.mounted_clients())
        constmounts = mounts.difference(path)
        changes: dict[str, dict[str, bool]] = {}
        for mp in path:
            ggi = enumerate(zip(mp, *constmounts))
            gi = (i for i, ch in ggi if ch[0] not in ch[1:])
            i: int | None = mp.find("/", next(gi, 0))
            if i == -1:
                i = None
            # TODO this might not work all the time when names are close
            pth, _, name = mp[:i].rpartition("/")
            if pth not in changes:
                changes[pth] = {}
            changes[pth][name] = mp in mounts
        for pth, value in changes.items():
            await self.signal(
                RpcMessage.signal(pth, "lschng", value, RpcMethodAccess.BROWSE)
            )

    async def start_serving(self, connect_timeout: float = 1.0) -> None:
        """Start accepting connections on all configured servers.

        :param connect_timeout: The timeout before we stop waiting for
           connections to be established.
        """

        def add(client: RpcClient) -> None:
            self.LoginClient(client, self)

        for name, url in self.config.listen.items():
            if name not in self.servers:
                self.servers[name] = await create_rpc_server(add, url)

        async with asyncio.timeout(connect_timeout):
            await asyncio.gather(
                *(
                    self.ConnectClient(
                        init_rpc_client(connection.url),
                        connection.url.login,
                        self,
                        user=connection.user,
                        reconnects=-1,
                    ).wait_for_login()
                    for connection in self.config.connections()
                ),
                return_exceptions=True,
            )

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

        async def client_disconnect(client: RpcBroker.Client) -> None:
            try:
                await client.disconnect()
            except Exception as exc:
                logger.error("Disconnect failed with: %s", exc)

        self.close()
        await self.wait_closed()
        await asyncio.gather(*(client_disconnect(c) for c in self.clients.values()))
