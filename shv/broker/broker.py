"""Common state for the RPC broker that works as server in the SHV network."""

from __future__ import annotations

import asyncio
import collections
import collections.abc
import contextlib
import logging
import random
import string
import time
import typing

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
from ..rpcparams import shvgett
from ..rpcserver import RpcServer, create_rpc_server
from ..rpcsubscription import RpcSubscription
from ..rpcurl import RpcLoginType
from ..simplebase import SimpleBase
from ..simpleclient import SimpleClient
from ..value import SHVType, is_shvmap
from .config import RpcBrokerConfig

logger = logging.getLogger(__name__)


class RpcBroker:
    """SHV RPC broker.

    The broker manages multiple RpcClient instances and exchanges messages
    between them.
    """

    class Client(SimpleBase):
        """Single client connected to the broker."""

        def __init__(
            self,
            client: RpcClient,
            broker: RpcBroker,
            *args: typing.Any,  # noqa ANN401
            user: RpcBrokerConfig.User | None = None,
            **kwargs: typing.Any,  # noqa ANN401
        ) -> None:
            super().__init__(client, *args, **kwargs)
            self.user: RpcBrokerConfig.User | None = user
            """Local user used to deduce access rights."""
            self.__broker = broker
            self.__broker_client_id = broker._register_client(self)
            self.__peer_is_broker: bool | None = None
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
        def active(self) -> bool:
            """Check if given client is actively communicating.

            Client can be inactive for example due to being disconnected, or in
            the middle of reset, or waiting for login.
            """
            return self.user is not None and self.client.connected

        async def peer_is_broker(self) -> bool:
            """Identify if peer this client is handle for is broker."""
            if self.__peer_is_broker is None:
                self.__peer_is_broker = False
                with contextlib.suppress(RpcError):
                    lsr = await self.call("", "ls", ".broker")
                    self.__peer_is_broker = lsr if isinstance(lsr, bool) else False
            return self.__peer_is_broker

        async def send(self, msg: RpcMessage) -> None:
            """Propagate given message to this peer.

            This is only wrapper around standard :meth:`_send`. We need to make
            it public because in Broker peers are propagating messages from one
            to another.

            :param msg: Message to be sent.
            """
            await self._send(msg)

        async def _message(self, msg: RpcMessage) -> None:
            assert self.user is not None

            if msg.is_request:
                # Set access granted to the level allowed by user
                access = self.user.access_level(msg.path, msg.method)
                if access is None:
                    return await self._send(
                        msg.make_response(
                            error=RpcError("No access", RpcErrorCode.METHOD_NOT_FOUND)
                        )
                    )
                msg.rpc_access = (
                    access
                    if msg.rpc_access is None or msg.rpc_access > access
                    else msg.rpc_access
                )
                # Append user ID
                if msg.user_id is not None:
                    bname = self.broker.config.name
                    msg.user_id += (
                        "," if msg.user_id else ""
                    ) + f"{bname}{':' if bname else ''}{self.user.name}"
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
                if (peer := self.__broker.get_client(cid)) is not None:
                    await peer.send(msg)

            elif msg.is_signal:
                await self.__broker.signal_from(msg, self)

        def _reset(self) -> None:
            self.__broker._unregister_client(self)  # pylint: disable=protected-access
            self.__peer_is_broker = None
            # pylint: disable=protected-access
            self.__broker_client_id = self.__broker._register_client(self)

        def _ls(self, path: str) -> typing.Iterator[str]:
            yield from super()._ls(path)
            if not path:
                yield ".broker"
            match path:
                case ".broker":
                    yield "currentClient"
                    yield "client"
                case ".broker/client":
                    yield from (
                        str(c.broker_client_id) for c in self.__broker.clients()
                    )
                case _:
                    for mnt, _ in self.broker.mounted_clients():
                        if not path:
                            yield mnt.split("/", maxsplit=1)[0]
                        elif mnt.startswith(path + "/"):
                            yield mnt[len(path) + 1 :].split("/", maxsplit=1)[0]

        def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
            yield from super()._dir(path)
            match path:
                case ".broker":
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
                case ".broker/currentClient":
                    yield RpcMethodDesc.getter("info", access=RpcMethodAccess.BROWSE)
                    yield RpcMethodDesc("subscribe", access=RpcMethodAccess.BROWSE)
                    yield RpcMethodDesc("unsubscribe", access=RpcMethodAccess.BROWSE)
                    yield RpcMethodDesc.getter(
                        "subscriptions", access=RpcMethodAccess.BROWSE
                    )

        async def _method_call(
            self,
            path: str,
            method: str,
            param: SHVType,
            access: RpcMethodAccess,
            user_id: str | None,
        ) -> SHVType:
            assert self.user is not None  # Otherwise handled in _message
            match path.split("/"):
                case [".broker"] if access >= RpcMethodAccess.SUPER_SERVICE:
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
                            return list(
                                c.broker_client_id for c in self.broker.clients()
                            )
                        case "mounts":
                            return [mnt for mnt, _ in self.broker.mounted_clients()]
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
                case [".broker", "currentClient"]:
                    match method:
                        case "info":
                            return self.infomap()
                        case "subscriptions":
                            return [
                                s.to_shv() for s in self.__broker.subscriptions(self)
                            ]
                        case "subscribe":
                            sub = RpcSubscription.from_shv(param)
                            return await self.__broker.subscribe(sub, self)
                        case "unsubscribe":
                            sub = RpcSubscription.from_shv(param)
                            return await self.__broker.unsubscribe(sub, self)
            return await super()._method_call(path, method, param, access, user_id)

        def infomap(self) -> SHVType:
            """Produce Map with client's info.

            This is info provided to administator to inform it about this
            client.
            """
            return {
                "clientId": self.broker_client_id,
                "userName": self.user.name if self.user is not None else None,
                "mountPoint": self.__broker.client_mountpoint(self),
                "subscriptions": [
                    s.to_shv() for s in self.__broker.subscriptions(self)
                ],
                "idleTime": int((time.monotonic() - self.client.last_receive) * 1000),
                "idleTimeMax": int(self.IDLE_TIMEOUT * 1000),
            }

        async def disconnect(self) -> None:  # noqa: D102
            logger.info("Disconnecting client with ID %d", self.broker_client_id)
            self.__broker._unregister_client(self)  # pylint: disable=protected-access
            await super().disconnect()

    class LoginClient(Client):
        """Broker's client that expects login from client."""

        APP_NAME = "pyshvbroker"
        """Name reported as application name for pyshvbroker."""

        IDLE_TIMEOUT_LOGIN: float = 5
        """:attr:`IDLE_TIMEOUT` set for clients without user.

        This is intentionally shorter to quickly disconnect inactive clients
        that are not participating in SHV RPC.
        """

        def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:  # noqa ANN204
            super().__init__(*args, **kwargs)
            self.IDLE_TIMEOUT = self.IDLE_TIMEOUT_LOGIN
            self._nonce: str = ""

        async def _loop(self) -> None:
            activity_task = asyncio.create_task(self._activity_loop())
            await super()._loop()
            activity_task.cancel()
            with contextlib.suppress(asyncio.exceptions.CancelledError):
                await activity_task

            self.broker._unregister_client(self)  # pylint: disable=protected-access
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
            # Login is required before we start handling messages as we would.
            if self.user is None:
                if msg.is_request:
                    await self._send(self._message_login(msg))
                return
            await super()._message(msg)

        def _message_login(self, msg: RpcMessage) -> RpcMessage:
            if not msg.path:
                if msg.method == "hello":
                    self._nonce = "".join(random.choices(string.hexdigits, k=10))  # noqa S311
                    return msg.make_response({"nonce": self._nonce})
                if self._nonce and msg.method == "login":
                    param = msg.param
                    if not is_shvmap(param):
                        return msg.make_response(
                            error=RpcInvalidParamsError("Invalid type of parameters")
                        )
                    self.user = self.broker.config.login(
                        shvgett(param, ("login", "user"), str, ""),
                        shvgett(param, ("login", "password"), str, ""),
                        self._nonce,
                        RpcLoginType(
                            shvgett(
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
                    mount_point = shvgett(
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
                        self.broker.mount_client(self, mount_point)
                    self.IDLE_TIMEOUT = float(
                        shvgett(
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

        APP_NAME = "pyshvbroker-client"
        """Name reported as application name for pyshvbroker connection."""

        def __init__(
            self,
            *args: typing.Any,  # noqa ANN204
            target_mount_point: str | None = None,
            **kwargs: typing.Any,  # noqa ANN204
        ) -> None:
            super().__init__(*args, **kwargs)
            self.target_mount_point = target_mount_point

        async def _login(self) -> None:
            await super()._login()
            self.broker.mount_client(self, self.target_mount_point)

        # TODO possibly add info about where it is connect to the infomap but we
        # must not disclouse login information

    def __init__(self, config: RpcBrokerConfig) -> None:
        self.config = config
        """Configuration of the RPC Broker."""
        self.servers: dict[str, RpcServer] = {}
        """All servers managed by Broker where keys are their configured names."""
        self._clients: dict[int, RpcBroker.Client] = {}
        self._subs: dict[RpcSubscription, set[int]] = {}
        self._mounts: dict[str, int] = {}
        self._subsubs: dict[str, collections.Counter[RpcSubscription]] = {}
        self.__last_caller_id = -1

    def _register_client(self, client: Client) -> int:
        """Register client that is called by :class:`Client` initialization."""
        # TODO try to reuse older caller IDs to send smaller messages but we
        # need to do it only after some given delay. We can safe time of client
        # disconnect to the self.clients and use that to identify when we can
        # reuse caller id.
        self.__last_caller_id += 1
        self._clients[self.__last_caller_id] = client
        return self.__last_caller_id

    def _unregister_client(self, client: Client) -> None:
        """Unregister client that is called by :class:`Client` reset and teardown."""
        self.mount_client(client, None)
        for subs in self._subs.values():
            subs.discard(client.broker_client_id)
        self._clients.pop(client.broker_client_id, None)

    def get_client(self, cid: int | str) -> Client | None:
        """Lookup client with given ID.

        :param cid: ID of the client either as string or as integer.
        :return: :class:`RpcBroker.Client` when such client is located and ``None``
            otherwise.
        """
        try:
            return self._clients[cid if isinstance(cid, int) else int(cid, 10)]
        except (ValueError, KeyError):
            return None

    def client_on_path(self, path: str) -> tuple[Client, str] | None:
        """Locate client mounted on given path.

        :return: client associated with this mount point and path relative to
            the client or None if there is no such client.
        """
        if path.startswith(".broker/client/"):
            pth = path.split("/")
            client = self.get_client(pth[2])
            return (client, "/".join(pth[3:])) if client else None

        # Note: we do not allow recursive mount points and thus first match is the
        # correct and the only client.
        for mnt, cid in self._mounts.items():
            if path.startswith(mnt + "/") or path == mnt:
                return self._clients[cid], path[len(mnt) + 1 :]
        return None

    def clients(self) -> collections.abc.Iterator[Client]:
        """Iterate over all clients of the broker."""
        yield from self._clients.values()

    def mounted_clients(self) -> collections.abc.Iterator[tuple[str, Client]]:
        """Goes through all clients and provides those active and mounted."""
        return (
            (mnt, self._clients[cid])
            for mnt, cid in self._mounts.items()
            if self._clients[cid].active
        )

    def mount_client(self, client: Client, mount_point: str | None) -> asyncio.Task:
        """Mount given client on given mount point.

        :param client: The client ID or object that should be mounted.
        :param mount_point: The mount point where client should be mounted.
        :return: Asyncio task you can await to make sure that mount is fully
          propagated.
        """
        cid = client.broker_client_id
        if mount_point is not None:
            mount_point = mount_point.rstrip("/")
        if mount_point and any(
            mnt.startswith(mount_point + "/")
            for mnt, mntcid in self._mounts.items()
            if mntcid != cid
        ):
            raise ValueError("Path already mounted")
        oldmnt = self.client_mountpoint(client)
        if oldmnt:
            self._mounts.pop(oldmnt, None)
            logger.info("Client with ID %d is no longer mounted on: %s", cid, oldmnt)
        if mount_point:
            self._mounts[mount_point] = cid
            logger.info("Client with ID %d is now mounted on: %s", cid, mount_point)
        return asyncio.create_task(self.__mount_client(client, oldmnt, mount_point))

    async def __mount_client(
        self, client: Client, oldmnt: str | None, newmnt: str | None
    ) -> None:
        prev = set(self._subsubs.pop(oldmnt, {}).keys()) if oldmnt else set()
        if client.active and await client.peer_is_broker():
            if newmnt:
                self._subsubs[newmnt] = collections.Counter(
                    s for sub in self._subs if (s := sub.relative_to(newmnt))
                )
                for s in self._subsubs[newmnt]:
                    if s in prev:
                        prev.discard(s)
                    else:
                        await client.call(
                            ".broker/currentClient"
                            if await client.peer_is_shv3()
                            else ".broker/app",
                            "subscribe",
                            s.to_shv(not await client.peer_is_shv3()),
                        )
            for s in prev:
                await client.call(
                    ".broker/currentClient"
                    if await client.peer_is_shv3()
                    else ".broker/app",
                    "unsubscribe",
                    s.to_shv(not await client.peer_is_shv3()),
                )

        await self._signal_mount_point_change(*(mnt for mnt in (oldmnt, newmnt) if mnt))

    def client_mountpoint(self, client: Client) -> str | None:
        """Get mount point for this client.

        :param client: The client ID or object that mount point should be
          received for.
        :return: The mount point of the client or ``None`` in case there is
          none.
        """
        try:
            return next(
                mnt
                for mnt, cid in self._mounts.items()
                if cid == client.broker_client_id
            )
        except StopIteration:
            return None

    def subscriptions(
        self, client: Client | None = None
    ) -> collections.abc.Iterator[RpcSubscription]:
        """Iterate over subscriptions this broker manages.

        :param client: The optional filtering over client's subscriptions.
        :return: Iterator over subscriptions.
        """
        yield from (
            s
            for s, v in self._subs.items()
            if client is None or client.broker_client_id in v
        )

    async def subscribe(self, subscription: RpcSubscription, client: Client) -> bool:
        """Add given subscription as being requested by given client."""
        assert client.user is not None
        if subscription in self._subs:
            self._subs[subscription].add(client.broker_client_id)
            return False
        self._subs[subscription] = {client.broker_client_id}
        # Propagate subscription to the sub-brokers
        for mnt, subc in self.mounted_clients():
            if not await subc.peer_is_broker():
                continue
            if sub := subscription.relative_to(mnt):
                if mnt not in self._subsubs:
                    self._subsubs[mnt] = collections.Counter()
                self._subsubs[mnt][sub] += 1
                if self._subsubs[mnt][sub] == 1:
                    await subc.call(
                        ".broker/currentClient"
                        if await subc.peer_is_shv3()
                        else ".broker/app",
                        "subscribe",
                        sub.to_shv(),
                    )
        return True

    async def unsubscribe(self, subscription: RpcSubscription, client: Client) -> bool:
        """Remove given subscription as being requested by given client."""
        if subscription not in self._subs:
            return False
        self._subs[subscription].discard(client.broker_client_id)
        if self._subs[subscription]:
            return True
        del self._subs[subscription]
        # Propagate unsubscribe to the sub-brokers
        for mnt, subc in self.mounted_clients():
            if not await subc.peer_is_broker():
                continue
            if sub := subscription.relative_to(mnt):
                self._subsubs[mnt][sub] -= 1
                if self._subsubs[mnt][sub] == 0:
                    del self._subsubs[mnt][sub]
                    await subc.call(
                        ".broker/currentClient"
                        if await subc.peer_is_shv3()
                        else ".broker/app",
                        "unsubscribe",
                        sub.to_shv(),
                    )
        return True

    async def signal(self, msg: RpcMessage) -> None:
        """Send signal to the broker's clients.

        :param msg: Signal message to be sent.
        """
        msgaccess = msg.rpc_access or RpcMethodAccess.READ
        for sub, clients in self._subs.items():
            if not sub.applies(msg.path, msg.signal_name, msg.source):
                continue
            for cid in clients:
                client = self._clients[cid]
                if not client.active:
                    continue
                assert client.user is not None
                access = client.user.access_level(msg.path, msg.method)
                if access is None or access < msgaccess:
                    continue
                await client.send(msg)

    async def signal_from(self, msg: RpcMessage, client: Client) -> None:
        """Send signal to the broker's client as comming from given client.

        :param msg: Signal message to be sent.
        :param client: Client ID or object signal should be propagated from.
        """
        if mnt := self.client_mountpoint(client):
            msg.path = mnt + ("/" if msg.path else "") + msg.path
            await self.signal(msg)

    async def _signal_mount_point_change(self, *path: str) -> None:
        """Send lsmod signal for node changes for given mount points.

        The state of the mount point can be deduced from the current list of
        them.

        You most likely do not want to call this if you are just a Broker user.
        It is used by broker's clients to inform all peers about mount point
        changes. Think about before you use this in your application!
        """
        mounts = set(self._mounts)
        constmounts = mounts.difference(path)
        changes: dict[str, dict[str, bool]] = {}
        for mp in path:
            ggi = enumerate(zip(mp, *constmounts, strict=False))
            gi = (i for i, ch in ggi if ch[0] not in ch[1:])
            i = mp.find("/", next(gi, 0))
            pth, _, name = mp[: i if i >= 0 else None].rpartition("/")
            if pth not in changes:
                changes[pth] = {}
            changes[pth][name] = mp in mounts
        for pth, value in changes.items():
            await self.signal(
                RpcMessage.signal(pth, "lsmod", "ls", value, RpcMethodAccess.BROWSE)
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
                logger.error("Disconnect failed", exc_info=exc)

        self.close()
        await self.wait_closed()
        await asyncio.gather(*(client_disconnect(c) for c in self._clients.values()))
