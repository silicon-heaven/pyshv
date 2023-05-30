"""Single connection of the broker."""
import asyncio
import collections.abc
import dataclasses
import enum
import importlib.metadata
import logging
import random
import time
import typing

from ..rpcclient import RpcClient
from ..rpcerrors import RpcErrorCode
from ..rpcmessage import RpcMessage
from ..rpcmethod import RpcMethodAccess, RpcMethodDesc, RpcMethodSignature
from ..rpcurl import RpcLoginType
from ..simpleclient import SimpleClient
from ..value import SHVType, shvget
from .rpcbrokerconfig import RpcBrokerConfig

if typing.TYPE_CHECKING:
    from .rpcbroker import RpcBroker


logger = logging.getLogger(__name__)


class RpcBrokerClient(SimpleClient):
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

    @dataclasses.dataclass(frozen=True)
    class Subscription:
        """Single subscription."""

        path: str
        method: str

    def __init__(
        self,
        client: RpcClient,
        client_id: int | None,
        broker: "RpcBroker",
        broker_client_id: int,
    ):
        super().__init__(client, client_id)
        self.broker: RpcBroker = broker
        """Broker this client is part of."""
        self.broker_client_id: int = broker_client_id
        """Identifier assigned to the client in the broker."""
        self.mount_point: list[str] = []
        """Mount point for this client split by '/'."""
        self.subscriptions: set[RpcBrokerClient.Subscription] = set()
        """Set of all subscriptions."""
        self.state = self.State.CONNECTED
        """Specifies state of the client login process."""
        self.user: RpcBrokerConfig.User | None = None
        """User used to login to the broker."""
        self._nonce = "".join(random.choice("0123456789abcdef") for _ in range(8))

    async def _loop(self) -> None:
        await super()._loop()
        logger.info("Client disconnected: %s", self.broker_client_id)
        self.broker.clients.pop(self.broker_client_id, None)

    async def _keep_alive_loop(self) -> None:
        while not self.client.writer.is_closing():
            t = time.monotonic() - self.client.last_activity
            if t < self.IDLE_TIMEOUT:
                await asyncio.sleep(self.IDLE_TIMEOUT - t)
            else:
                await self.disconnect()

    async def _message(self, msg: RpcMessage) -> None:
        if self.state == self.State.CONNECTED:
            return await self.client.send_rpc_message(await self._message_hello(msg))
        if self.state == self.State.HELLO:
            return await self.client.send_rpc_message(await self._message_login(msg))

        path = msg.shv_path() or ""
        method = msg.method() or ""

        if msg.is_request():
            # Set upper access granted to the level allowed by user
            assert self.user is not None
            access = self.user.access_level(path, method)
            msgaccess = msg.access_grant()
            if msgaccess is None or msgaccess > access:
                msg.set_access_grant(access)
            # Check if we should delegate it or handle it ourself
            if (cpath := self.broker.peer_on_path(path)) is None:
                return await super()._message(msg)
            # Propagate to some peer
            msg.set_caller_ids(list(msg.caller_ids() or ()) + [self.broker_client_id])
            msg.set_shv_path(cpath[1])
            await cpath[0].client.send_rpc_message(msg)

        if msg.is_response():
            cids = list(msg.caller_ids() or ())
            if not cids:  # no caller IDs means this is message for us
                return await super()._message(msg)
            cid = cids.pop()
            msg.set_caller_ids(cids)
            try:
                peer = self.broker.clients[cid]
            except KeyError:
                return
            if peer is not None and not peer.client.writer.is_closing():
                await peer.client.send_rpc_message(msg)

        if msg.is_signal():
            # TODO this might add unnecessary /
            fullpath = "/".join(self.mount_point + [path])
            msg.set_shv_path(fullpath)
            for client in self.broker.clients.values():
                if client is self:
                    continue
                if client.get_subscription(fullpath, method) is not None:
                    await client.client.send_rpc_message(msg)

    async def _message_hello(self, msg: RpcMessage) -> RpcMessage:
        resp = msg.make_response()
        if msg.is_request() and msg.method() == "hello":
            self.state = self.State.HELLO
            resp = msg.make_response()
            resp.set_result({"nonce": self._nonce})
        else:
            resp.set_shverror(RpcErrorCode.INVALID_REQUEST, "Only 'hello' is allowed")
        return resp

    async def _message_login(self, msg: RpcMessage) -> RpcMessage:
        resp = msg.make_response()
        if not msg.is_request() or msg.method() != "login":
            resp.set_shverror(RpcErrorCode.INVALID_REQUEST, "Only 'login' is allowed")
            return resp
        params = msg.params()
        resp = msg.make_response()
        if isinstance(params, collections.abc.Mapping):
            self.user = self.broker.config.login(
                shvget(params, ("login", "user"), "", str),
                shvget(params, ("login", "password"), "", str),
                self._nonce,
                RpcLoginType(
                    shvget(params, ("login", "type"), RpcLoginType.SHA1.value, str)
                ),
            )
            if self.user is None:
                resp.set_shverror(RpcErrorCode.METHOD_CALL_EXCEPTION, "Invalid login")
                return resp
            mount_point = shvget(params, ("options", "device", "mountPoint"), "", str)
            if self.broker.peer_on_path(mount_point) is not None:
                resp.set_shverror(
                    RpcErrorCode.METHOD_CALL_EXCEPTION, "Mount point already mounted"
                )
                return resp
            # TODO rights to mount to this path?
            self.mount_point = mount_point.split("/") if mount_point else []
            self.IDLE_TIMEOUT = float(
                shvget(
                    params, ("options", "idleWatchDogTimeOut"), self.IDLE_TIMEOUT, int
                )
            )
            resp.set_result({"clientId": self.broker_client_id})
            self.state = self.State.LOGIN
        else:
            resp.set_shverror(RpcErrorCode.INVALID_PARAMS, "Invalid type of parameters")
        return resp

    def _ls(self, path: str) -> typing.Iterator[tuple[str, bool | None]]:
        pth = path.split("/") if path else []
        if len(pth) > 0 and pth[0] == ".broker":
            if len(pth) == 1:
                yield ("app", False)
                yield ("clients", True)  # There is always at least this client
                yield ("currentClient", False)
                return
            if pth[1] in ("app", "currentClient") and len(pth) == 2:
                return
            if pth[1] == "clients":
                if len(pth) == 2:
                    for cid, c in self.broker.clients.items():
                        yield (str(cid), True)
                    return
                try:
                    cid = int(pth[2], 10)
                except ValueError:
                    pass
                else:
                    if cid in self.broker.clients:
                        if len(pth) == 3:
                            yield ("app", None)
                            return
                        return
        else:
            res: set[tuple[str, bool | None]] = set()
            if len(pth) == 0:
                res.add((".broker", True))
            res |= {
                (
                    c.mount_point[len(pth)],
                    None if len(c.mount_point) - 1 == len(pth) else True,
                )
                for c in self.broker.clients.values()
                if c.mount_point and c.mount_point[: len(pth)] == pth
            }
            if res:
                yield from sorted(iter(res))
                return

        yield from super()._ls(path)

    def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
        yield from super()._dir(path)
        pth = path.split("/") if path else []
        if len(pth) > 0 and pth[0] == ".broker":
            if len(pth) == 2 and pth[1] == "app":
                yield RpcMethodDesc("ping")
                yield RpcMethodDesc(
                    "subscribe",
                    RpcMethodSignature.RET_PARAM,
                    access=RpcMethodAccess.READ,
                )
                yield RpcMethodDesc(
                    "unsubscribe",
                    RpcMethodSignature.RET_PARAM,
                    access=RpcMethodAccess.READ,
                )
                yield RpcMethodDesc(
                    "rejectNotSubscribed",
                    RpcMethodSignature.RET_PARAM,
                    access=RpcMethodAccess.READ,
                )
                yield RpcMethodDesc.getter(
                    "mountPoints", access=RpcMethodAccess.SERVICE
                )
                return
            if len(pth) == 2 and pth[1] == "currentClient":
                yield RpcMethodDesc.getter("clientId")
                yield RpcMethodDesc.getter("mountPoint")
                return
            if len(pth) > 2 and pth[1] == "clients":
                if len(pth) == 3:
                    yield RpcMethodDesc.getter(
                        "userName", access=RpcMethodAccess.SERVICE
                    )
                    yield RpcMethodDesc.getter(
                        "mountPoint", access=RpcMethodAccess.SERVICE
                    )
                    yield RpcMethodDesc.getter(
                        "subscriptions", access=RpcMethodAccess.SERVICE
                    )
                    yield RpcMethodDesc(
                        "dropClient",
                        RpcMethodSignature.RET_VOID,
                        access=RpcMethodAccess.SERVICE,
                    )
                    yield RpcMethodDesc.getter(
                        "idleTime", access=RpcMethodAccess.SERVICE
                    )
                    yield RpcMethodDesc.getter(
                        "idleTimeMax", access=RpcMethodAccess.SERVICE
                    )

    async def _method_call(
        self, path: str, method: str, access: RpcMethodAccess, params: SHVType
    ) -> SHVType:
        if path == ".broker/app":
            if method == "ping":
                return None
            if method == "subscribe":
                method = shvget(params, "method", "chng", str)
                path = shvget(params, "path", "", str)
                # TODO we do not check the access level. The user might subscribe to the
                # node that it does not have access and thus get values he should not
                # see.
                self.subscriptions.add(self.Subscription(path, method))
                return None
            if method == "unsubscribe":
                method = shvget(params, "method", "chng", str)
                path = shvget(params, "path", "", str)
                try:
                    self.subscriptions.remove(self.Subscription(path, method))
                except KeyError:
                    return False
                return True
            if method == "rejectNotSubscribed":
                method = shvget(params, "method", "chng", str)
                path = shvget(params, "path", "", str)
                sub = self.get_subscription(path, method)
                if sub is not None:
                    self.subscriptions.remove(sub)
                    return True
                return False
            if method == "mountPoints" and access >= RpcMethodAccess.SERVICE:
                return {
                    "/".join(c.mount_point): c.broker_client_id
                    for c in self.broker.clients.values()
                    if c.mount_point
                }
        elif path == ".broker/currentClient":
            if method == "clientId":
                return self.broker_client_id
            if method == "mountPoint":
                return "/".join(self.mount_point) if self.mount_point else None
        elif path.startswith(".broker/clients/"):
            cidstr = path[16:]
            try:
                cid = int(cidstr, 10)
            except ValueError:
                pass
            else:
                if cid in self.broker.clients:
                    client = self.broker.clients[cid]
                    if client is not None and access >= RpcMethodAccess.SERVICE:
                        if method == "userName":
                            assert client.user is not None
                            return client.user.name
                        if method == "mountPoint":
                            return (
                                "/".join(self.mount_point) if self.mount_point else None
                            )
                        if method == "subscriptions":
                            return [
                                {"path": s.path, "method": s.method}
                                for s in client.subscriptions
                            ]
                        if method == "dropClient":
                            await client.disconnect()
                            return True
                        if method == "idleTime":
                            return int(
                                (time.monotonic() - client.client.last_activity) * 1000
                            )
                        if method == "idleTimeMax":
                            return int(self.IDLE_TIMEOUT * 1000)
        return await super()._method_call(path, method, access, params)

    def get_subscription(
        self, path: str, method: str
    ) -> typing.Optional["RpcBrokerClient.Subscription"]:
        """Get subscription matching given path and method.

        This is not exact get, it rather implements standard path and method
        lookup. Thus more specific paths are prefered.
        """
        subs = {s.path: s for s in self.subscriptions if s.method == method}
        pth = path.split("/")
        paths = ("/".join(pth[: len(pth) - i]) for i in range(len(pth)))
        return next((subs[path] for path in paths if path in subs), None)

    async def disconnect(self) -> None:
        logger.info("Disconnecting client: %d", self.broker_client_id)
        self.broker.clients.pop(self.broker_client_id, None)
        await super().disconnect()
