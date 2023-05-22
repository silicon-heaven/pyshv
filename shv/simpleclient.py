"""RPC client manager that provides facitility to simply connect to the broker."""
import asyncio
import collections.abc
import copy
import datetime
import enum
import logging
import typing

from .rpcclient import RpcClient, RpcProtocol
from .rpcerrors import (
    RpcError,
    RpcInvalidParamsError,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
)
from .rpcmessage import RpcMessage
from .value import SHVType, is_shvbool, is_shvnull, shvmeta, shvmeta_eq

logger = logging.getLogger(__name__)


class SimpleClient:
    """SHV client made simple to use.

    You most likely want to use this client instead of using RpcClient directly.

    Messages are handled in an asyncio loop and based on the type of the message
    the different operation is performed.
    """

    class LoginType(enum.Enum):
        """Enum specifying which login type should be used."""

        PLAIN = "PLAIN"
        """Plain login format should be used."""
        SHA1 = "SHA1"
        """Use hash algorithm SHA1 (preferred and common default)."""

    def __init__(self, client: RpcClient, client_id: int | None):
        self.client = client
        """The underlaying RPC client instance."""
        self.client_id = client_id
        """Client ID assigned on login by SHV broker."""
        self.task = asyncio.create_task(self._loop())
        """Task running the message handling loop."""
        self._calls_event: dict[int, asyncio.Event] = {}
        self._calls_msg: dict[int, RpcMessage] = {}

    @classmethod
    async def connect(
        cls,
        host: str | None,
        port: int = 3755,
        protocol: RpcProtocol = RpcProtocol.TCP,
        user: str | None = None,
        password: str | None = None,
        login_type: LoginType = LoginType.SHA1,
        login_options: dict[str, SHVType] | None = None,
    ) -> typing.Union["SimpleClient", None]:
        """Connect and login to the SHV broker.

        :param host: IP/Hostname (TCP) or socket path (LOCKAL_SOCKET)
        :param port: Port (TCP) to connect to
        :param protocol: Protocol used to connect to the server
        :param user: User name used to login
        :param password: Password used to login
        :param login_type: Type of the login to be used
        :param login_options: Options sent with login
        :raises RuntimeError: in case connection is already established
        """
        client = await RpcClient.connect(host, port, protocol)
        cid = await cls._login(client, user, password, login_type, login_options)
        if client.writer.is_closing():
            return None
        return cls(client, cid)

    async def disconnect(self) -> None:
        """Disconnect an existing connection.

        The call to the disconnect when client is not connected is silently
        ignored.
        """
        if self.client.writer.is_closing():
            return
        await self.client.disconnect()

    @staticmethod
    async def _login(
        client: RpcClient,
        user: str | None,
        password: str | None,
        login_type: LoginType,
        login_options: dict[str, SHVType] | None,
    ) -> int | None:
        """Perform login to the broker.

        The login need to be performed only once right after the connection is
        established.

        :returns: Client ID assigned by broker or `None` in case none was
            assigned.
        """
        # Note: The implementation here expects that broker won't sent any other
        # messages until login is actually performed. That is what happens but
        # it is not defined in any SHV design document as it seems.
        await client.call_shv_method(None, "hello")
        await client.read_rpc_message()
        # TODO support nonce
        params = {
            "login": {"password": password, "type": login_type.value, "user": user},
            "options": login_options,
        }
        logger.debug("LOGGING IN")
        await client.call_shv_method(None, "login", params)
        resp = await client.read_rpc_message()
        if resp is None:
            return None
        result = resp.result()
        logger.debug("LOGGED IN")
        cid = result.get("clientId", None) if isinstance(result, dict) else None
        if isinstance(cid, int):
            return cid
        return 0

    async def _loop(self) -> None:
        """Loop run in asyncio task to receive messages."""
        while msg := await self.client.read_rpc_message(throw_error=False):
            asyncio.create_task(self._message(msg))

    async def _message(self, msg: RpcMessage) -> None:
        """Handle every received message."""
        if msg.is_request():
            resp = msg.make_response()
            try:
                resp.set_result(
                    await self._method_call(msg.shv_path(), msg.method(), msg.params())
                )
            except RpcError as exp:
                resp.set_rpc_error(exp)
            except Exception as exp:
                resp.set_rpc_error(RpcMethodCallExceptionError(str(exp)))
            await self.client.send_rpc_message(resp)
        elif msg.is_response():
            rid = msg.request_id()
            assert rid is not None
            if rid in self._calls_event:
                self._calls_msg[rid] = msg
                self._calls_event.pop(rid).set()
        elif msg.is_signal():
            if msg.method() == "chng":
                await self._value_update(msg.shv_path(), msg.params())

    async def call(self, path: str, method: str, params: SHVType = None) -> SHVType:
        """Call given method on given path with given parameters.

        Note that this is coroutine and this it is up to you if you await it or
        use asyncio tasks.

        :param path: SHV path method is associated with.
        :param method: SHV method name to be called.
        :param params: Parameters passed to the called method.
        :returns: Return value on successful method call.
        :raises RpcError: The call result in error that is propagated by raising
            `RpcError` or its children based on the failure.
        """
        rid = self.client.next_request_id()
        event = asyncio.Event()
        self._calls_event[rid] = event
        await self.client.call_shv_method_with_id(rid, path, method, params)
        await event.wait()
        msg = self._calls_msg.pop(rid)
        err = msg.rpc_error()
        if err is not None:
            raise err
        return msg.result()

    async def ls(self, path: str) -> list[str]:
        """List child nodes of the node on the specified path.

        :params path: SHV path to the node we want children to be listed for.
        :returns: list of child nodes.
        :raises RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "ls")
        if not isinstance(res, list):
            raise RpcMethodCallExceptionError(f"Invalid result returned: {repr(res)}")
        return res

    async def ls_with_children(self, path: str) -> dict[str, bool]:
        """List child nodes of the node on the specified path.

        Compared to the :func:`ls` method this provides you also with info on
        children of the node. This can safe unnecessary listing requests when
        you are iterating over the tree.

        :params path: SHV path to the node we want children to be listed for.
        :returns: dictionary where keys are names of the nodes and values are
            booleans signaling presence of at least one child.
        :raises RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "ls", ("", 1))
        if not isinstance(res, list):
            raise RpcMethodCallExceptionError(f"Invalid result returned: {repr(res)}")
        return {v[0]: v[1] for v in res}

    async def dir(self, path: str) -> list[str]:
        """List methods associated with node on the specified path.

        :params path: SHV path to the node we want methods to be listed for.
        :returns: list of the node's methods.
        :raises RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "dir", ("", 0))
        if not isinstance(res, list):
            raise RpcMethodCallExceptionError(f"Invalid result returned: {repr(res)}")
        return res

    async def dir_details(self, path: str) -> dict[str, dict[str, SHVType]]:
        """List methods associated with node on the specified path.

        :params path: SHV path to the node we want methods to be listed for.
        :returns: list of the node's methods.
        :raises RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "dir")
        if not isinstance(res, list):
            raise RpcMethodCallExceptionError(f"Invalid result returned: {repr(res)}")
        print(res)
        return {v["name"]: v for v in res}

    async def subscribe(self, path: str) -> None:
        """Perform subscribe for signals on given path.

        Subscribe is always performed on the node itself as well as all its
        children.

        :params path: SHV path to the node to subscribe.
        """
        await self.call(".broker/app", "subscribe", path)

    async def unsubscribe(self, path: str) -> bool:
        """Perform unsubscribe for signals on given path.

        :params path: SHV path previously passed to :func:`subscribe`.
        :returns: ``True`` in case such subscribe was located and ``False``
            otherwise.
        """
        resp = await self.call(".broker/app", "unsubscribe", path)
        assert is_shvbool(resp)
        return bool(resp)

    async def _method_call(
        self,
        path: str | None,
        method: str | None,
        params: SHVType,
    ) -> SHVType:
        """Handle request in the provided message.

        You have to set some RpcMessage that is sent back as a response.
        """
        raise RpcMethodNotFoundError(f"No such path '{path}' or method '{method}'")

    async def _value_update(self, path: str | None, value: SHVType) -> None:
        """Handle value change (`chng` method)."""


class ValueClient(SimpleClient, collections.abc.Mapping):
    """SHV client made to track values more easily.

    This tailors to the use case of tracking and accessing various values more
    easily. You need to subscribe to specific path and this class automatically
    provides you with cached latest value as received through signals or fetched
    from logs (logs fetching has to be performed explicitly).

    To acess the value you can index this object with SHV path to it.
    """

    def __init__(self, client: RpcClient, client_id: int | None):
        super().__init__(client, client_id)
        self._registry: dict[str, SHVType] = {}
        self._handlers: dict[str, typing.Callable] = {}

    def __getitem__(self, key: str) -> SHVType:
        return self._registry[key]

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self._registry.keys())

    def __len__(self):
        return len(self._registry)

    async def _value_update(self, path: str | None, value: SHVType) -> None:
        path = path or ""
        handler = self._get_handler(path)
        if handler is not None and not shvmeta_eq(
            self._registry.get(path, None), value
        ):
            handler(self, path, value)
        self._registry[path] = value

    def _get_handler(self, path: str) -> None | typing.Callable:
        """Get the handler for the longest path match."""
        split_key = path.split("/")
        paths = (
            "/".join(split_key[: len(split_key) - i]) for i in range(len(split_key))
        )
        return next(
            (self._handlers[path] for path in paths if path in self._handlers),
            None,
        )

    def on_change(self, path: str, callback: typing.Callable | None) -> None:
        """Register new callback handler called when value changes.

        The handler is called right before value is updated and thus it is
        possible to access the old and new value is provided as an argument.

        To clear the callback on the specific path you can pass `None`.

        :param path:
        :param callback:
        """
        if callback is None:
            self._handlers.pop(path)
        else:
            self._handlers[path] = callback

    async def log_snapshot(self, path: str) -> None:
        """Get snapshot of the logs.

        Use this to receive old values.

        :param path: SHV path to the node with `getLog` method.
        """
        params: SHVType = {
            "recordCountLimit": 10000,
            "withPathsDict": True,
            "withSnapshot": True,
            "withTypeInfo": False,
            "since": datetime.datetime.now(),
        }
        result = await self.call(path, "getLog", params)
        if result:
            paths_dict = shvmeta(result).get("pathsDict", None)
            if isinstance(paths_dict, collections.abc.Sequence):
                for list_item in paths_dict:
                    if not isinstance(list_item, collections.abc.Sequence):
                        continue
                    idx = list_item[1]
                    if not isinstance(idx, int):
                        continue
                    value = list_item[2]
                    spath = paths_dict[idx]
                    if not isinstance(spath, str):
                        continue
                    await self._value_update(spath, value)


class DeviceClient(SimpleClient):
    """SHV client tailored for device implementation.

    Device in SHV is client that supports ``ls`` and ``dir`` methods and thus
    provides some tree of nodes that have method associated with it.

    To use it you should create new class based on it and implement your ``_ls``
    and ``_dir`` methods.
    """

    class MethodSignature(enum.IntEnum):
        """Signature of the method."""

        VOID_VOID = 0
        VOID_PARAM = 1
        RET_VOID = 2
        RET_PARAM = 3

    class MethodFlags(enum.IntFlag):
        """Flags assigned to the methods."""

        SIGNAL = 1 << 0
        GETTER = 1 << 1
        SETTER = 1 << 2
        LARGE_RESULT_HINT = 1 << 3

    @classmethod
    async def connect(
        cls,
        host: str | None,
        port: int = 3755,
        protocol: RpcProtocol = RpcProtocol.TCP,
        user: str | None = None,
        password: str | None = None,
        login_type: SimpleClient.LoginType = SimpleClient.LoginType.SHA1,
        login_options: dict[str, SHVType] | None = None,
        device_id: str = "",
        mount_point: str = "",
    ) -> typing.Union["SimpleClient", None]:
        """Connect and login to the SHV broker for devices.

        Please see documentation for :func:`SimpleClient.connect` as well as
        this one.

        :param device_id: Identifier for this device.
        :param mount_point: Mount point request on connected SHV broker.
        """
        options: dict[str, SHVType] = {
            "device": {
                **({"deviceId": device_id} if device_id is not None else {}),
                **({"mountPoint": mount_point} if mount_point is not None else {}),
            },
        }
        if login_options is not None:
            options.update({k: v for k, v in login_options.items() if k != "device"})
        return await super(DeviceClient, cls).connect(
            host, port, protocol, user, password, login_type, options
        )

    async def _method_call(
        self,
        path: str | None,
        method: str | None,
        params: SHVType,
    ) -> SHVType:
        if method == "ls":
            if not is_shvnull(params) and not (
                isinstance(params, list)
                and len(params) == 2
                and isinstance(params[0], str)
                and isinstance(params[1], int)
            ):
                raise RpcInvalidParamsError("Use Null or list with path and attributes")
            path = path or ""
            children = False
            if isinstance(params, list):
                path = "/".join(filter(lambda v: v, (path, params[0])))
                if params[1] & 0x1:
                    children = True
            lsres = await self._ls(path)
            if lsres is None:
                raise RpcMethodNotFoundError("No such node")
            if not children:
                return list(val[0] for val in lsres)
            return lsres
        if method == "dir":
            if (
                not is_shvnull(params)
                and not isinstance(params, str)
                and not (
                    isinstance(params, list)
                    and len(params) == 2
                    and isinstance(params[0], str)
                    and isinstance(params[1], int)
                )
            ):
                raise RpcInvalidParamsError(
                    "Use Null, string or list with path and attributes"
                )
            path = "/".join(
                filter(
                    lambda v: v,
                    (
                        path or "",
                        params if isinstance(params, str) else "",
                        params[0] if isinstance(params, list) else "",
                    ),
                )
            )
            dirres = await self._dir(path)
            if dirres is None:
                raise RpcMethodNotFoundError("No such node")
            dirres = [
                (
                    "dir",
                    self.MethodSignature.RET_PARAM,
                    self.MethodFlags(0),
                    "bws",
                    "",
                ),
                (
                    "ls",
                    self.MethodSignature.RET_PARAM,
                    self.MethodFlags(0),
                    "bws",
                    "",
                ),
                *dirres,
            ]
            if isinstance(params, list) and params[1] == 127:
                return list(
                    {
                        "name": v[0],
                        "signature": v[1],
                        "flags": v[2],
                        "accessGrant": v[3],
                        **({"description": v[4]} if v[4] else {}),
                    }
                    for v in dirres
                )
            return list(v[0] for v in dirres)
        return await super()._method_call(path, method, params)

    async def _ls(self, path: str) -> collections.abc.Sequence[tuple[str, bool]] | None:
        """Implement ``ls`` method for all nodes.

        The default implementation returns empty list for the root and ``None``
        otherwise. Your implementation should return list of child nodes. Every
        node should be tuple with its name and boolean signaling if there are
        some children.

        :param path: SHV path that should be listed.
        :returns: List of child nodes of the node on the path or ``None`` for
            invalid nodes.
        """
        return None if path else []

    async def _dir(
        self, path: str
    ) -> collections.abc.Sequence[
        tuple[str, MethodSignature, MethodFlags, str, str]
    ] | None:
        """Implement ``dir`` method for all nodes.

        The default implementation returns empty list for the root and ``None``
        otherwise. Your implementations needs to return list of methods where
        tuple has these fields:
        * Name of the method
        * Signature of the method
        * Flags for the method
        * Access rights script (for example ``"rd"`` or ``"wr"``)
        * Description of the method

        Note that the called automatically prefixes your list with ``ls`` and
        ``dir`` signatures.

        :param path: SHV path method should be listed for.
        :returns: List of methods associated with given node or ``None` for
            invalid nodes.
        """
        return None if path else []
