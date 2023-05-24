"""RPC client manager that provides facitility to simply connect to the broker."""
import asyncio
import collections.abc
import datetime
import hashlib
import logging
import time
import typing
import warnings

from .rpcclient import RpcClient
from .rpcerrors import (
    RpcError,
    RpcInvalidParamsError,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
)
from .rpcmessage import RpcMessage
from .rpcmethod import RpcMethodAccess, RpcMethodFlags, RpcMethodSignature
from .rpcurl import RpcLoginType, RpcUrl
from .value import SHVType, is_shvbool, is_shvnull, shvmeta, shvmeta_eq

logger = logging.getLogger(__name__)


class SimpleClient:
    """SHV client made simple to use.

    You most likely want to use this client instead of using RpcClient directly.

    Messages are handled in an asyncio loop and based on the type of the message
    the different operation is performed.
    """

    IDLE_TIMEOUT = 180
    """Number of seconds before we are disconnected from the broker automatically."""

    def __init__(self, client: RpcClient, client_id: int | None):
        self.client = client
        """The underlaying RPC client instance."""
        self.client_id = client_id
        """Client ID assigned on login by SHV broker."""
        self.task = asyncio.create_task(self._loop())
        """Task running the message handling loop."""
        self.keep_alive_task = asyncio.create_task(self._keep_alive_loop())
        """Task running the keep alive loop."""
        self._last_activity = time.monotonic()
        self._calls_event: dict[int, asyncio.Event] = {}
        self._calls_msg: dict[int, RpcMessage] = {}

    @classmethod
    async def connect(
        cls,
        url: RpcUrl,
        login_options: dict[str, SHVType] | None = None,
    ) -> typing.Union["SimpleClient", None]:
        """Connect and login to the SHV broker.

        :param url: SHV RPC URL to the broker
        :param login_options: Additional options sent with login
        """
        client = await RpcClient.connect(url.host, url.port, url.protocol)
        options = url.login_options()
        if login_options:
            options.update(login_options)
        cid = await cls.login(
            client, url.username, url.password, url.login_type, options
        )
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
        self.keep_alive_task.cancel()

    @classmethod
    async def login(
        cls,
        client: RpcClient,
        username: str | None,
        password: str | None,
        login_type: RpcLoginType,
        login_options: dict[str, SHVType] | None,
    ) -> int | None:
        """Perform login to the broker.

        The login need to be performed only once right after the connection is
        established.

        :return: Client ID assigned by broker or `None` in case none was
            assigned.
        """
        # Note: The implementation here expects that broker won't sent any other
        # messages until login is actually performed. That is what happens but
        # it is not defined in any SHV design document as it seems.
        await client.call_shv_method(None, "hello")
        resp = await client.read_rpc_message()
        if resp is None:
            return None
        resl = resp.result()
        assert isinstance(resl, collections.abc.Mapping)

        nonce = resl.get("nonce", None)
        if login_type is RpcLoginType.SHA1:
            assert isinstance(nonce, str)
            m = hashlib.sha1()
            m.update(nonce.encode("utf-8"))
            m.update((password or "").encode("utf-8"))
            password = m.hexdigest()
        params: SHVType = {
            "login": {"password": password, "type": login_type.value, "user": username},
            "options": {
                "idleWatchDogTimeOut": int(cls.IDLE_TIMEOUT),
                **(login_options if login_options else {}),  # type: ignore
            },
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

    async def _keep_alive_loop(self) -> None:
        """Loop run in asyncio task to send pings to the broker when idling."""
        idlet = self.IDLE_TIMEOUT / 2
        while not self.client.writer.is_closing():
            t = time.monotonic() - self._last_activity
            if t < idlet:
                await asyncio.sleep(idlet - t)
            await self.client.call_shv_method(".broker/app", "ping")
            self._last_activity = time.monotonic()

    async def _message(self, msg: RpcMessage) -> None:
        """Handle every received message."""
        if msg.is_request():
            resp = msg.make_response()
            method = msg.method()
            assert method  # is ensured by is_request but not detected by mypy
            try:
                resp.set_result(
                    await self._method_call(
                        msg.shv_path() or "",
                        method,
                        msg.access_grant() or RpcMethodAccess.BROWSE,
                        msg.params(),
                    )
                )
            except RpcError as exp:
                resp.set_rpc_error(exp)
            except Exception as exp:
                resp.set_rpc_error(RpcMethodCallExceptionError(str(exp)))
            await self.client.send_rpc_message(resp)
            self._last_activity = time.monotonic()
        elif msg.is_response():
            rid = msg.request_id()
            assert rid is not None
            if rid in self._calls_event:
                self._calls_msg[rid] = msg
                self._calls_event.pop(rid).set()
        elif msg.is_signal():
            if msg.method() == "chng":
                await self._value_update(msg.shv_path() or "", msg.params())

    async def call(self, path: str, method: str, params: SHVType = None) -> SHVType:
        """Call given method on given path with given parameters.

        Note that this is coroutine and this it is up to you if you await it or
        use asyncio tasks.

        :param path: SHV path method is associated with.
        :param method: SHV method name to be called.
        :param params: Parameters passed to the called method.
        :return: Return value on successful method call.
        :raise RpcError: The call result in error that is propagated by raising
            `RpcError` or its children based on the failure.
        """
        rid = self.client.next_request_id()
        event = asyncio.Event()
        self._calls_event[rid] = event
        await self.client.call_shv_method_with_id(rid, path, method, params)
        self._last_activity = time.monotonic()
        await event.wait()
        msg = self._calls_msg.pop(rid)
        err = msg.rpc_error()
        if err is not None:
            raise err
        return msg.result()

    async def ls(self, path: str) -> list[str]:
        """List child nodes of the node on the specified path.

        :param path: SHV path to the node we want children to be listed for.
        :return: list of child nodes.
        :raise RpcMethodNotFoundError: when there is no such path.
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

        :param path: SHV path to the node we want children to be listed for.
        :return: dictionary where keys are names of the nodes and values are
            booleans signaling presence of at least one child.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "ls", ("", 1))
        if not isinstance(res, list):
            raise RpcMethodCallExceptionError(f"Invalid result returned: {repr(res)}")
        return {v[0]: v[1] for v in res}

    async def dir(self, path: str) -> list[str]:
        """List methods associated with node on the specified path.

        :param path: SHV path to the node we want methods to be listed for.
        :return: list of the node's methods.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "dir", ("", 0))
        if not isinstance(res, list):
            raise RpcMethodCallExceptionError(f"Invalid result returned: {repr(res)}")
        return res

    async def dir_details(self, path: str) -> dict[str, dict[str, SHVType]]:
        """List methods associated with node on the specified path.

        :param path: SHV path to the node we want methods to be listed for.
        :return: list of the node's methods.
        :raise RpcMethodNotFoundError: when there is no such path.
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

        :param path: SHV path to the node to subscribe.
        """
        await self.call(".broker/app", "subscribe", path)

    async def unsubscribe(self, path: str) -> bool:
        """Perform unsubscribe for signals on given path.

        :param path: SHV path previously passed to :func:`subscribe`.
        :return: ``True`` in case such subscribe was located and ``False``
            otherwise.
        """
        resp = await self.call(".broker/app", "unsubscribe", path)
        assert is_shvbool(resp)
        return bool(resp)

    async def _method_call(
        self, path: str, method: str, access: RpcMethodAccess, params: SHVType
    ) -> SHVType:
        """Handle request in the provided message.

        You have to set some RpcMessage that is sent back as a response.

        :param path: SHV path to the node the method is associated with.
        :param method: method requested to be called.
        :param access: access level of the client specified in the request.
        :param params: Parameters to be passed to the called method.
        :return: result of the method call. To report error you should raise
            :exc:`RpcError`.
        """
        raise RpcMethodNotFoundError(f"No such path '{path}' or method '{method}'")

    async def _value_update(self, path: str, value: SHVType) -> None:
        """Handle value change (`chng` method)."""


class ValueClient(SimpleClient, collections.abc.Mapping):
    """SHV client made to track values more easily.

    This tailors to the use case of tracking and accessing various values more
    easily. You need to subscribe to specific path and this class automatically
    provides you with cached latest value as received through signals or fetched
    from logs (logs fetching has to be performed explicitly).

    To access subscribed value you can index this object with SHV path to it.
    """

    def __init__(self, client: RpcClient, client_id: int | None):
        super().__init__(client, client_id)
        self._cache: dict[str, SHVType] = {}
        self._handlers: dict[str, typing.Callable] = {}

    def __getitem__(self, key: str) -> SHVType:
        return self._cache[key]

    def __iter__(self) -> typing.Iterator[str]:
        return iter(self._cache.keys())

    def __len__(self):
        return len(self._cache)

    async def _value_update(self, path: str, value: SHVType) -> None:
        handler = self._get_handler(path)
        if handler is not None and not shvmeta_eq(self._cache.get(path, None), value):
            handler(self, path, value)
        self._cache[path] = value

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

    async def prop_get(self, path: str) -> SHVType:
        """Get value from the property associated with the node on given path."""
        return await self.call(path, "get")

    async def prop_set(self, path: str, value: SHVType) -> None:
        """Set value to the property associated with the node on given path."""
        await self.call(path, "set", value)

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

    async def get_snapshot(self, path: str) -> None:
        """Get snapshot of data using get methods.

        This provides a way for you to initialize cache without logs. It
        iterates over SHV tree and calls any get method it encounters.
        """
        # TODO rewrite this to use ls_with_children to safe on method calls
        if "get" in await self.dir(path) and path not in self._cache:
            self._cache[path] = await self.prop_get(path)
        for node in await self.ls(path):
            await self.get_snapshot("/".join((path, node)))


class DeviceClient(SimpleClient):
    """SHV client tailored for device implementation.

    Device in SHV is client that supports ``ls`` and ``dir`` methods and thus
    provides some tree of nodes that have method associated with it.

    To use it you should create new class based on it and implement your ``_ls``
    and ``_dir`` methods.
    """

    @classmethod
    async def connect(
        cls,
        url: RpcUrl,
        login_options: dict[str, SHVType] | None = None,
    ) -> typing.Union["SimpleClient", None]:
        if not url.device_id and not url.device_mount_point:
            warnings.warn("You should specify device ID or device mount point!")
        return await super(DeviceClient, cls).connect(url, login_options)

    async def _method_call(
        self, path: str, method: str, access: RpcMethodAccess, params: SHVType
    ) -> SHVType:
        if method == "ls":
            if not is_shvnull(params) and not (
                isinstance(params, list)
                and len(params) == 2
                and isinstance(params[0], str)
                and isinstance(params[1], int)
            ):
                raise RpcInvalidParamsError("Use Null or list with path and attributes")
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
                        path,
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
                    RpcMethodSignature.RET_PARAM,
                    RpcMethodFlags(0),
                    RpcMethodAccess.BROWSE,
                    "",
                ),
                (
                    "ls",
                    RpcMethodSignature.RET_PARAM,
                    RpcMethodFlags(0),
                    RpcMethodAccess.BROWSE,
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
                        "accessGrant": RpcMethodAccess.tostr(v[3]),
                        **({"description": v[4]} if v[4] else {}),
                    }
                    for v in dirres
                )
            return list(v[0] for v in dirres)
        return await super()._method_call(path, method, access, params)

    async def _ls(self, path: str) -> collections.abc.Sequence[tuple[str, bool]] | None:
        """Implement ``ls`` method for all nodes.

        The default implementation returns empty list for the root and ``None``
        otherwise. Your implementation should return list of child nodes. Every
        node should be tuple with its name and boolean signaling if there are
        some children.

        :param path: SHV path that should be listed.
        :return: List of child nodes of the node on the path or ``None`` for
            invalid nodes.
        """
        return None if path else []

    async def _dir(
        self, path: str
    ) -> collections.abc.Sequence[
        tuple[str, RpcMethodSignature, RpcMethodFlags, RpcMethodAccess, str]
    ] | None:
        """Implement ``dir`` method for all nodes.

        The default implementation returns ``None`` for all paths ``_ls`` does
        (it calls it to check) and empty list otherwise. Your implementations
        needs to return list of methods where tuple has these fields:

        * Name of the method
        * Signature of the method
        * Flags for the method
        * Access rights script (for example ``"rd"`` or ``"wr"``)
        * Description of the method

        Note that the caller automatically prefixes your list with ``ls`` and
        ``dir`` signatures.

        :param path: SHV path method should be listed for.
        :return: List of methods associated with given node or ``None`` for
            invalid nodes.
        """
        return None if self._ls(path) is None else []
