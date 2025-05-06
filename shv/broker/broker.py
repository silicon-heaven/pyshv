"""Common state for the RPC broker that works as server in the SHV network."""

from __future__ import annotations

import abc
import asyncio
import collections
import collections.abc
import contextlib
import logging
import secrets
import time
import typing

from ..rpcaccess import RpcAccess
from ..rpcdir import RpcDir
from ..rpcerrors import (
    RpcError,
    RpcInvalidParamError,
    RpcLoginRequiredError,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
)
from ..rpclogin import RpcLogin
from ..rpcmessage import RpcMessage
from ..rpcparam import shvargt
from ..rpcri import rpcri_match, rpcri_relative_to
from ..rpctransport import RpcClient, RpcServer, create_rpc_server, init_rpc_client
from ..shvbase import SHVBase
from ..shvclient import SHVClient
from ..value import SHVType
from .config import RpcBrokerConfigABC, RpcBrokerRoleABC
from .utils import nmax, nmin

logger = logging.getLogger(__name__)


class RpcBroker:
    """SHV RPC broker.

    The broker manages multiple RpcClient instances and exchanges messages
    between them.
    """

    class Client(SHVBase):
        """Single client connected to the broker."""

        def __init__(
            self,
            client: RpcClient,
            broker: RpcBroker,
            *args: typing.Any,  # noqa ANN401
            **kwargs: typing.Any,  # noqa ANN401
        ) -> None:
            super().__init__(client, *args, **kwargs)
            self._send_queue: collections.deque[RpcMessage]
            self._send_queue = collections.deque(maxlen=16)
            self.__broker = broker
            self.__broker_client_id: int | None = None
            self.__peer_is_broker: bool | None = None

        @property
        def broker(self) -> RpcBroker:
            """Broker this client is part of."""
            return self.__broker

        @property
        def broker_client_id(self) -> int | None:
            """Identifier assigned to the client in the broker."""
            return self.__broker_client_id

        @property
        def local_user_id(self) -> str:
            """Provide user ID for this Broker client."""
            # The minimal is the broker's name (child must extend this)
            return self.__broker.config.name

        @property
        @abc.abstractmethod
        def role(self) -> RpcBrokerRoleABC | None:
            """Role assigned in the broker.

            Can be used to query configuration for different rules for this
            client.
            """

        async def peer_is_broker(self) -> bool:
            """Identify if peer this client is handle for is broker."""
            if self.__peer_is_broker is None:
                self.__peer_is_broker = False
                with contextlib.suppress(RpcError):
                    lsr = await self.call("", "ls", ".broker")
                    self.__peer_is_broker = lsr if isinstance(lsr, bool) else False
            return self.__peer_is_broker

        def send(self, msg: RpcMessage) -> None:
            """Propagate given message to this peer.

            This provides a way for other clients to queue messages to be sent
            by this client. THis is because Broker peers are propagating
            messages from one to the other. This won't block but it also won't
            ensure that message won't be dropped.

            :param msg: Message to be sent.
            """
            self._send_queue.append(msg)
            self._idle_message_ready()

        def _idle_message(self) -> RpcMessage | None:
            if self._send_queue:
                return self._send_queue.popleft()
            return super()._idle_message()

        async def disconnect(self) -> None:  # noqa: D102
            logger.info("Disconnecting client with ID %s", str(self.broker_client_id))
            self._unregister()
            await super().disconnect()

        async def _message(self, msg: RpcMessage) -> None:
            assert self.role is not None
            match msg.type:
                case RpcMessage.Type.REQUEST | RpcMessage.Type.REQUEST_ABORT:
                    # Set access granted to the level allowed by the role
                    access = self.role.access_level(msg.path, msg.method)
                    if access is None:
                        if msg.path not in {
                            "",
                            ".app",
                            ".broker",
                            ".broker/currentClient",
                        }:
                            await self._send(
                                msg.make_response(RpcMethodNotFoundError("No access"))
                            )
                            return
                        access = RpcAccess.BROWSE
                    # Limit access level in the message
                    msg.rpc_access = (
                        access
                        if msg.rpc_access is None or msg.rpc_access > access
                        else msg.rpc_access
                    )
                    # Append user ID
                    if msg.user_id is not None:
                        msg.user_id += (";" if msg.user_id else "") + self.local_user_id
                    # Check if we should handle it ourself (else propagate it)
                    if (cpath := self.__broker.client_on_path(msg.path)) is None:
                        await super()._message(msg)
                        return
                    # Protect sub-broker currentClient access
                    if cpath[1] == ".broker/currentClient" and (
                        msg.method in {"subscribe", "unsubscribe"}
                        or msg.rpc_access < RpcAccess.SUPER_SERVICE
                    ):
                        await self._send(
                            msg.make_response(RpcMethodNotFoundError("No access"))
                        )
                        return
                    # Propagate to some peer
                    assert self.__broker_client_id is not None
                    msg.caller_ids = [*msg.caller_ids, self.__broker_client_id]
                    msg.path = cpath[1]
                    cpath[0].send(msg)

                case (
                    RpcMessage.Type.RESPONSE
                    | RpcMessage.Type.RESPONSE_ERROR
                    | RpcMessage.Type.RESPONSE_DELAY
                ):
                    cids = list(msg.caller_ids)
                    if not cids:  # no caller IDs means this is message for us
                        await super()._message(msg)
                        return
                    cid = cids.pop()
                    msg.caller_ids = cids
                    if (peer := self.__broker.get_client(cid)) is not None:
                        peer.send(msg)

                case RpcMessage.Type.SIGNAL:
                    self.__broker.signal_from(msg, self)

        def _reset(self) -> None:
            self.__peer_is_broker = None
            self._unregister()

        def _register(self) -> None:
            if self.__broker_client_id is not None:
                self.__broker.unregister_client(self)
                self.__broker_client_id = None
            self.__broker_client_id = self.__broker.register_client(self)

        def _unregister(self) -> None:
            if self.__broker_client_id is not None:
                self.__broker.unregister_client(self)
                self.__broker_client_id = None

        def _ls(self, path: str) -> collections.abc.Iterator[str]:
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

        def _dir(self, path: str) -> collections.abc.Iterator[RpcDir]:
            yield from super()._dir(path)
            match path:
                case ".broker":
                    yield RpcDir.getter("name", "n", "s", access=RpcAccess.BROWSE)
                    yield RpcDir(
                        "clientInfo",
                        param="i",
                        result="!clientInfo|n",
                        access=RpcAccess.SUPER_SERVICE,
                    )
                    yield RpcDir(
                        "mountedClientInfo",
                        param="s",
                        result="!clientInfo|n",
                        access=RpcAccess.SUPER_SERVICE,
                    )
                    yield RpcDir.getter(
                        "clients", "n", "[i]", access=RpcAccess.SUPER_SERVICE
                    )
                    yield RpcDir.getter(
                        "mounts", "n", "[s]", access=RpcAccess.SUPER_SERVICE
                    )
                    yield RpcDir(
                        "disconnectClient", param="i", access=RpcAccess.SUPER_SERVICE
                    )
                case ".broker/currentClient":
                    yield RpcDir("info", RpcDir.Flag.GETTER, result="!clientInfo")
                    yield RpcDir(
                        "subscribe",
                        param="s|[s:RPCRI,i:TTL]",
                        result="b",
                        access=RpcAccess.BROWSE,
                    )
                    yield RpcDir(
                        "unsubscribe", param="s", result="b", access=RpcAccess.BROWSE
                    )
                    yield RpcDir.getter(
                        "subscriptions", result="{i|n}", access=RpcAccess.BROWSE
                    )

        async def _method_call(self, request: SHVBase.Request) -> SHVType:
            assert self.role is not None  # Otherwise handled in _message
            match request.path.split("/"):
                case [".broker"] if request.access >= RpcAccess.SUPER_SERVICE:
                    match request.method:
                        case "name":
                            return self.__broker.config.name
                        case "clientInfo":
                            if not isinstance(request.param, int):
                                raise RpcInvalidParamError("Use Int")
                            client = self.broker.get_client(request.param)
                            return client.infomap() if client is not None else None
                        case "mountedClientInfo":
                            if not isinstance(request.param, str):
                                raise RpcInvalidParamError("Use String with SHV path")
                            client_pth = self.broker.client_on_path(request.param)
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
                            if not isinstance(request.param, int):
                                raise RpcInvalidParamError("Use Int")
                            client = self.broker.get_client(request.param)
                            if client is None:
                                raise RpcMethodCallExceptionError(
                                    f"No such client with ID: {request.param}"
                                )
                            await client.disconnect()
                            return None
                case [".broker", "currentClient"]:
                    match request.method:
                        case "info":
                            return self.infomap()
                        case "subscriptions":
                            return self._subscriptions()
                        case "subscribe":
                            sub = shvargt(request.param, 0, str)
                            ttl = shvargt(request.param, 1, int, -1)
                            return await self.__broker.subscribe(
                                self, sub, None if ttl < 0 else ttl
                            )
                        case "unsubscribe":
                            if not isinstance(request.param, str):
                                raise RpcInvalidParamError("Use string")
                            return await self.__broker.unsubscribe(self, request.param)
            return await super()._method_call(request)

        def infomap(self) -> dict[str, SHVType]:
            """Produce Map with client's info.

            This is info provided to administator to inform it about this
            client.
            """
            return {
                "clientId": self.broker_client_id,
                "mountPoint": self.__broker.client_mountpoint(self),
                "subscriptions": self._subscriptions(),
                "idleTime": int((time.monotonic() - self.client.last_receive) * 1000),
                "idleTimeMax": int(self.IDLE_TIMEOUT * 1000),
                "role": self.role.name if self.role is not None else None,
                "client": str(self.client),
            }

        def _subscriptions(self) -> dict[str, int | None]:
            now = time.time()
            return {
                str(ri): int(deadline - now) if deadline is not None else None
                for ri, deadline in self.__broker.subscriptions(self)
                if deadline is None or deadline > now
            }

    class LoginClient(Client):
        """Broker's client that expects login from client."""

        APP_NAME = "pyshvbroker"
        """Name reported as application name for pyshvbroker."""

        IDLE_TIMEOUT_LOGIN: float = 5
        """:attr:`shv.SHVBase.IDLE_TIMEOUT` set for clients without user.

        This is intentionally shorter to quickly disconnect inactive clients
        that are not participating in SHV RPC.
        """

        def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:  # noqa ANN204
            super().__init__(*args, **kwargs)
            self.IDLE_TIMEOUT = self.IDLE_TIMEOUT_LOGIN
            self._role: RpcBrokerRoleABC | None = None
            self._login: RpcLogin | None = None
            self._nonce: str = ""

        @property
        def role(self) -> RpcBrokerRoleABC | None:
            """Role of the user used to login to the broker."""
            return self._role

        @property
        def local_user_id(self) -> str:
            """Provide user ID for this Broker client."""
            s = super().local_user_id
            n = self._login.username if self._login else "?"
            return f"{n}{':' if s else ''}{s}"

        async def _loop(self) -> None:
            activity_task = asyncio.create_task(self._activity_loop())
            try:
                await super()._loop()
            finally:
                activity_task.cancel()
                with contextlib.suppress(asyncio.exceptions.CancelledError):
                    await activity_task

                self._unregister()
            self.client.disconnect()
            await self.client.wait_disconnect()

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
            if self._role is not None:
                return await super()._message(msg)
            if not msg.type == RpcMessage.Type.REQUEST:
                return  # Ignore anything other than requests before login
            if not msg.path:
                if msg.method == "hello":
                    if not self._nonce:
                        self._nonce = secrets.token_hex(5)  # ten characters
                    await self._send(msg.make_response({"nonce": self._nonce}))
                    return
                if self._nonce and msg.method == "login":
                    try:
                        self._login = RpcLogin.from_shv(msg.param)
                        self._role = self.broker.config.login(self._login, self._nonce)
                    except RpcError as exp:
                        await self._send(msg.make_response(exp))
                        return
                    if self._role is None:
                        error = RpcMethodCallExceptionError("Invalid login")
                        await self._send(msg.make_response(error))
                        return
                    try:
                        self._register()
                    except ValueError as exc:
                        error = RpcMethodCallExceptionError(str(exc))
                        await self._send(msg.make_response(error))
                        return
                    self.IDLE_TIMEOUT = float(
                        self._login.idle_timeout or type(self).IDLE_TIMEOUT
                    )
                    device_id = self._login.device_id
                    logger.info(
                        "Client %d logged in as user: %s%s",
                        self.broker_client_id,
                        self._login.username,
                        f" (deviceId={device_id})" if device_id else "",
                    )
                    await self._send(msg.make_response())
                    return
            await self._send(
                msg.make_response(
                    RpcLoginRequiredError(
                        "Use hello and login methods"
                        if self._nonce
                        else "Use hello method"
                    )
                )
            )

        def _reset(self) -> None:
            super()._reset()
            self._nonce = ""
            self._login = None
            self._role = None

        def infomap(self) -> dict[str, SHVType]:
            """Produce Map with client's info.

            This is info provided to administator to inform it about this
            client.

            On top of the standard one it provides also info about device ID.
            """
            assert self._login is not None  # Should not be called before login
            return {
                **super().infomap(),
                "userName": self._login.username,
                "deviceId": self._login.device_id,
            }

    class ConnectClient(SHVClient, Client):
        """Broker client that activelly connects to some other peer."""

        APP_NAME = "pyshvbroker-client"
        """Name reported as application name for pyshvbroker connection."""

        def __init__(
            self,
            *args: typing.Any,  # noqa ANN204
            role: RpcBrokerRoleABC,
            **kwargs: typing.Any,  # noqa ANN204
        ) -> None:
            super().__init__(*args, **kwargs)
            self._role = role

        @property
        def role(self) -> RpcBrokerRoleABC:  # noqa D102
            return self._role

        async def _login(self) -> None:
            await super()._login()
            self._register()

    def __init__(self, config: RpcBrokerConfigABC) -> None:
        self.config = config
        """Configuration of the RPC Broker."""
        self.servers: dict[str, RpcServer] = {}
        """All servers managed by Broker where keys are their configured names."""
        self._clients: dict[int, RpcBroker.Client] = {}
        self._mounts: dict[str, int] = {}
        self._reserved_mount_points: set[str] = set()
        self._subs: dict[str, dict[int, float | None]] = {}
        """Subscriptions.

        RI filters signals and value contains map of all client IDs this
        subscription was requested by and specified end of the subscription
        live for that specific client.
        """
        self._subs_task: asyncio.Task | None = None
        self.__subs_changed = asyncio.Event()
        self.__next_caller_id = 0

    def register_client(self, client: Client) -> int:
        """Register RPC peer to the broker.

        :param client: Client object to register.
        :returns: Assigned client's ID in this broker.
        :raise ValueError: when registering with these parameters is for some
          reason not possible.
        """
        if client.role is None:
            raise ValueError("Client must have role assigned.")
        if client.broker_client_id is not None:
            raise ValueError("Client already registered.")
        # TODO try to reuse older caller IDs to send smaller messages but we
        # need to do it only after some given delay. We can save time of client
        # disconnect to the self.clients and use that to identify when we can
        # reuse caller id.
        cid = self.__next_caller_id
        self.__next_caller_id += 1
        self._clients[cid] = client
        mount_point: str | None = None
        if mount_point := client.role.mount_point(set(self._mounts)):
            mount_point = mount_point.rstrip("/")
            if mount_point.partition("/")[0] in {"", ".app", ".broker", ".device"}:
                raise ValueError("Mount point is not allowed")
            if any(
                mount_point == mnt
                or mnt.startswith(mount_point + "/")
                or mount_point.startswith(mnt + "/")
                for mnt in self._mounts
            ):
                raise ValueError("Mount point is already mounted")
            self.__lsmod_msg(mount_point, True)
            self._mounts[mount_point] = cid
        for ri in client.role.initial_subscriptions():
            self._subs.setdefault(ri, {})[cid] = None
        self._subs_notify()
        logger.info(
            "Client registered to broker with ID %d%s",
            cid,
            f" and mount point {mount_point}" if mount_point else "",
        )
        return cid

    def unregister_client(self, client: Client) -> None:
        """Unregister RPC peer and thus remove it from broker.

        :param client: Client object registration to be removed.
        :raise ValueError: when passed client is not registered.
        """
        cid = client.broker_client_id
        if cid is None:
            raise ValueError("Client not registered")
        if cid not in self._clients:
            raise ValueError("Client is not registered in this broker")
        if mount_point := self.client_mountpoint(client):
            del self._mounts[mount_point]
            self.__lsmod_msg(mount_point, False)
        for subs in self._subs.values():
            subs.pop(cid, None)
        self._subs = {n: v for n, v in self._subs.items() if v}
        del self._clients[cid]
        self._subs_notify()
        logger.info("Client with ID %d unregistered from broker", cid)

    def __lsmod_msg(self, path: str, new: bool) -> None:
        root = ""
        for node in path.split("/"):
            nroot = root + ("/" if root else "") + node
            if any(m.startswith(nroot) for m in self._mounts):
                root = nroot
            else:
                break
        self.signal(RpcMessage.signal(root, "lsmod", "ls", {node: new}))

    def get_client(self, cid: int | str) -> Client | None:
        """Lookup client with given ID.

        :param cid: ID of the client either as string or as integer.
        :return: :class:`RpcBroker.Client` when such client is located and ``None``
            otherwise.
        """
        try:
            return self._clients.get(cid if isinstance(cid, int) else int(cid, 10))
        except ValueError:
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
        """Iterate over all clients participating in the broker."""
        yield from self._clients.values()

    def mounted_clients(self) -> collections.abc.Iterator[tuple[str, Client]]:
        """Goes through participating clients and provides those with mount point."""
        return ((mnt, self._clients[cid]) for mnt, cid in self._mounts.items())

    def client_mountpoint(self, client: Client) -> str | None:
        """Get mount point for this client.

        :param client: The client object that mount point should be received for.
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
    ) -> collections.abc.Iterator[tuple[str, float | None]]:
        """Iterate over subscriptions this broker manages.

        :param client: The optional filtering over client's subscriptions.
        :return: Iterator over subscriptions and their deadline (when they are
          no longer valid).
        """
        yield from (
            (
                s,
                v[client.broker_client_id]
                if client is not None and client.broker_client_id is not None
                else nmax(iter(v.values())),
            )
            for s, v in self._subs.items()
            if client is None or client.broker_client_id in v
        )

    async def subscribe(self, client: Client, ri: str, ttl: int | None = None) -> bool:
        """Add given subscription as being requested by given client.

        :param client: Client object this subscription is requested by.
        :param ri: The resource identifier for the subscription.
        :param ttl: Time to live for this subscription.
        :returns: ``False`` if this subscription was already present or ``True``
          if it is a new one.
        """
        if client.broker_client_id is None:
            raise ValueError("Client must be registered")
        subset = self._subs.setdefault(ri, {})
        res = client.broker_client_id not in subset
        subset[client.broker_client_id] = time.time() + ttl if ttl is not None else None
        self._subs_notify()
        return res

    async def unsubscribe(self, client: Client, ri: str) -> bool:
        """Remove given subscription as being requested by given client.

        :param client: Client object this subscription is requested by.
        :param ri: The resource identifier for the subscription.
        :returns: ``False`` if no subscription was removed and ``True``
          otherwise.
        """
        if client.broker_client_id is None:
            raise ValueError("Client must be registered")
        if ri not in self._subs:
            return False
        self._subs[ri].pop(client.broker_client_id, None)
        self._subs = {n: v for n, v in self._subs.items() if v}
        self._subs_notify()
        return True

    def signal(self, msg: RpcMessage) -> None:
        """Send signal to the broker's clients.

        :param msg: Signal message to be sent.
        """
        msgaccess = msg.rpc_access or RpcAccess.READ
        cids: set[int] = set()
        for sub, clients in self._subs.items():
            if rpcri_match(sub, msg.path, msg.source, msg.signal_name):
                cids |= {c for c in clients if c is not None}
        for cid in cids:
            client = self._clients[cid]
            assert client.role is not None
            access = client.role.access_level(msg.path, msg.source)
            if access is not None and access >= msgaccess:
                client.send(msg)

    def signal_from(self, msg: RpcMessage, client: Client) -> None:
        """Send signal to the broker's client as comming from given client.

        :param msg: Signal message to be sent.
        :param client: Client ID or object signal should be propagated from.
        """
        if mnt := self.client_mountpoint(client):
            msg.path = mnt + ("/" if msg.path else "") + msg.path
            self.signal(msg)

    def _subs_notify(self) -> None:
        """Alert :meth:`_subs_loop` that changes to the subscriptions was made.

        This not only notifies running subscription loop but also starts it when
        it is not running.
        """
        if self._subs_task is None or self._subs_task.done():
            self._subs_task = asyncio.create_task(self._subs_loop())
        else:
            self.__subs_changed.set()

    async def _subs_loop(self) -> None:
        """Subscriptions management loop.

        This loop manages subscriptions in broker. It removes timed out
        subscriptions and propagates needed subscriptions to the sub-brokers.
        """
        loop = asyncio.get_running_loop()
        subsubs: dict[str, float] = {}
        subbrokers: set[int] = set()
        # TODO use heuristic to increase the delay for long term subscriptions
        while True:
            now = loop.time()
            # Remove any timed-out subscriptions
            for ri in self._subs:
                self._subs[ri] = {
                    k: v for k, v in self._subs[ri].items() if v is None or v > now
                }
            self._subs = {k: v for k, v in self._subs.items() if v}
            # Propagate subscriptions to subbrokers
            nsubbrokers: set[int] = set()
            for mnt, client in self.mounted_clients():
                # TODO we can't await in this loop to not modify the source
                # TODO this relies heavilly on SHV 3.0 and not all mounted
                # brokers will have that. Do we want to just ignore those or
                # do we want to implemented dedicated support for them?
                if (
                    await client.peer_shv_version() < (3, 0)
                    or not await client.peer_is_broker()
                ):
                    continue
                for ri in self._subs:
                    if (
                        client.broker_client_id not in subbrokers
                        or subsubs.get(ri, now) <= now
                    ) and (rri := rpcri_relative_to(ri, mnt)):
                        client.send(
                            RpcMessage.request(
                                ".broker/currentClient", "subscribe", [str(rri), 120]
                            )
                        )
                assert client.broker_client_id is not None
                nsubbrokers.add(client.broker_client_id)
            subbrokers = nsubbrokers
            subsubs = {
                ri: (now + 60)
                if ri not in subsubs or subsubs[ri] <= now
                else subsubs[ri]
                for ri in self._subs
            }
            # Now identify when we should do this again
            dlsub = nmin(*(iter(d.values()) for d in self._subs.values()))
            deadline = nmin(iter(subsubs.values()), dlsub)
            if dlsub is None and not subbrokers:
                return  # Terminate this task as it is not required
            # Now wait for event or deadline
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout_at(deadline):
                    await self.__subs_changed.wait()
                    self.__subs_changed.clear()

    async def start_serving(self, connect_timeout: float = 1.0) -> None:
        """Start accepting connections on all configured servers.

        This also initializes configured connections.

        :param connect_timeout: The timeout before we stop waiting for
           connections to be established.
        """

        def add(client: RpcClient) -> None:
            self.LoginClient(client, self)

        # We create our connect clients first to ensure that they get
        # preferential setup (and also preferential error detection).
        connect_clients = []
        for url, role in self.config.connections():
            connect_clients.append(
                self.ConnectClient(
                    init_rpc_client(url), url.login, self, role=role, reconnects=-1
                )
            )
            if mount_point := role.mount_point(self._reserved_mount_points):
                self._reserved_mount_points.add(mount_point)

        # Now start all servers so clients can connect
        for url in self.config.listens():
            surl = str(url)
            if surl not in self.servers:
                self.servers[surl] = await create_rpc_server(add, url)

        # Lastly wait specified time for clients to connect
        async with asyncio.timeout(connect_timeout):
            await asyncio.gather(
                *(client.wait_for_login() for client in connect_clients),
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

        for server in self.servers.values():
            server.terminate()
        await asyncio.gather(
            *(client_disconnect(c) for c in self._clients.values()),
            *(s.wait_terminated() for s in self.servers.values()),
        )
        if self._subs_task is not None:
            if not self._subs_task.done():
                self._subs_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._subs_task
