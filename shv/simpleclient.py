"""RPC client manager that provides facitility to simply connect to the broker."""
import asyncio
import collections.abc
import hashlib
import logging
import time
import traceback
import typing

from .rpcclient import RpcClient, connect_rpc_client
from .rpcerrors import (
    RpcError,
    RpcInvalidParamsError,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
)
from .rpcmessage import RpcMessage
from .rpcmethod import RpcMethodAccess, RpcMethodDesc, RpcMethodSignature
from .rpcurl import RpcLoginType, RpcUrl
from .shvversion import SHV_VERSION_MAJOR, SHV_VERSION_MINOR
from .value import SHVType, is_shvbool, is_shvnull

logger = logging.getLogger(__name__)


class SimpleClient:
    """SHV client made simple to use.

    You most likely want to use this client instead of using RpcClient directly.

    Messages are handled in an asyncio loop and based on the type of the message
    the different operation is performed.
    """

    IDLE_TIMEOUT: float = 180
    """Number of seconds before we are disconnected from the broker automatically."""

    APP_NAME: str = "pyshv"
    """Name of the application reported to the SHV.

    You can change this value in child class to report a more accurate
    application name.
    """
    APP_VERSION: str = "unknown"
    """Version of the application reported to the SHV.

    You should change this value in child class to report a correct number.
    """

    def __init__(self, client: RpcClient, client_id: int | None):
        self.client = client
        """The underlaying RPC client instance."""
        self.client_id = client_id
        """Client ID assigned on login by SHV broker."""
        self.task = asyncio.create_task(self._loop())
        """Task running the message handling loop."""
        self._calls_event: dict[int, asyncio.Event] = {}
        self._calls_msg: dict[int, RpcMessage] = {}
        self.__peer_is_shv3: None | bool = None

    @classmethod
    async def connect(
        cls,
        url: RpcUrl,
        login_options: dict[str, SHVType] | None = None,
    ) -> typing.Union["SimpleClient", None]:
        """Connect and login to the SHV broker.

        :param url: SHV RPC URL to the broker
        :param login_options: Additional options sent with login
        :return: Connected instance.
        """
        client = await connect_rpc_client(url)
        cid = await cls.urllogin(client, url)
        if not client.connected():
            return None
        return cls(client, cid)

    async def disconnect(self) -> None:
        """Disconnect an existing connection.

        The call to the disconnect when client is not connected is silently
        ignored.
        """
        if not self.client.connected():
            return
        await self.client.disconnect()
        await self.task

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

        :param: client: Connected client the login should be performed on.
        :param username: User's name used to login.
        :param password: Password used to authenticate the user.
        :param login_type: The password format and login process selection.
        :param login_options: Login options.
        :return: Client ID assigned by broker or `None` in case none was assigned.
        """
        # Note: The implementation here expects that broker won't sent any other
        # messages until login is actually performed. That is what happens but
        # it is not defined in any SHV design document as it seems.
        await client.send(RpcMessage.request(None, "hello"))
        resp = await client.receive()
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
        await client.send(RpcMessage.request(None, "login", params))
        resp = await client.receive()
        if resp is None:
            return None
        result = resp.result()
        logger.debug("LOGGED IN")
        cid = result.get("clientId", None) if isinstance(result, dict) else None
        if isinstance(cid, int):
            return cid
        return 0

    @classmethod
    async def urllogin(
        cls,
        client: RpcClient,
        url: RpcUrl,
        login_options: dict[str, SHVType] | None = None,
    ) -> int | None:
        """Variation of :meth:`login` that takes arguments from RPC URL.

        :param: client: Connected client the login should be performed on.
        :param url: RPC URL with login info.
        :param login_options: Additional custom login options that are not supported by
            RPC URL.
        :return: Client ID assigned by broker or `None` in case none was assigned.
        """
        options = url.login_options()
        if login_options:
            options.update(login_options)
        return await cls.login(
            client, url.username, url.password, url.login_type, options
        )

    async def _loop(self) -> None:
        """Loop run in asyncio task to receive messages."""
        activity_task = asyncio.create_task(self._activity_loop())
        while msg := await self.client.receive(raise_error=False):
            asyncio.create_task(self._message(msg))
        activity_task.cancel()
        try:
            await activity_task
        except asyncio.exceptions.CancelledError:
            pass

    async def _activity_loop(self) -> None:
        """Loop run alongside with :meth:`_loop` to send pings to the broker when idling."""
        idlet = self.IDLE_TIMEOUT / 2
        while self.client.connected():
            t = time.monotonic() - self.client.last_send
            if t < idlet:
                await asyncio.sleep(idlet - t)
            else:
                await self.client.send(
                    RpcMessage.request(
                        ".app" if await self._peer_is_shv3() else ".broker/currentClient",
                        "ping",
                    )
                )

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
                        msg.rpc_access_grant() or RpcMethodAccess.BROWSE,
                        msg.params(),
                    )
                )
            except RpcError as exp:
                resp.set_rpc_error(exp)
            except Exception as exc:
                resp.set_rpc_error(
                    RpcMethodCallExceptionError(
                        "".join(traceback.format_exception(exc))
                    )
                )
            await self.client.send(resp)
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
        msg = RpcMessage.request(path, method, params)
        rid = msg.request_id()
        assert rid is not None
        event = asyncio.Event()
        self._calls_event[rid] = event
        await self.client.send(msg)
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

    async def ls_has_child(self, path: str, name: str) -> bool:
        """Use ``ls`` method to check for child.

        :param path: SHV path to the node with possible child of given name.
        :param name: Name of the child node.
        :return: ``True`` if there is such child and ``False`` if not.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "ls", name)
        if not isinstance(res, bool):
            raise RpcMethodCallExceptionError(f"Invalid result returned: {repr(res)}")
        return res

    async def dir(self, path: str) -> list[RpcMethodDesc]:
        """List methods associated with node on the specified path.

        :param path: SHV path to the node we want methods to be listed for.
        :return: list of the node's methods.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "dir")
        if isinstance(res, list):
            return [RpcMethodDesc.frommap(m) for m in res]
        raise RpcMethodCallExceptionError(f"Invalid result returned: {repr(res)}")

    async def dir_description(self, path: str, name: str) -> RpcMethodDesc | None:
        """Get method description associated with node on the specified path.

        :param path: SHV path to the node we want methods to be listed for.
        :param name: Name of the method description to be received for.
        :return: Method description or ``None`` in case there is no such method.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "dir", name)
        if isinstance(res, list):  # TODO backward compatibility
            res = res[0] if len(res) == 1 else None
        if is_shvnull(res):
            return None
        if isinstance(res, dict):
            return RpcMethodDesc.frommap(res)
        raise RpcMethodCallExceptionError(f"Invalid result returned: {repr(res)}")

    async def subscribe(self, path: str) -> None:
        """Perform subscribe for signals on given path.

        Subscribe is always performed on the node itself as well as all its
        children.

        :param path: SHV path to the node to subscribe.
        """
        await self.call(
            ".app/broker/currentClient" if await self._peer_is_shv3() else ".broker/app",
            "subscribe",
            {"method": "chng", "path": path},
        )

    async def unsubscribe(self, path: str) -> bool:
        """Perform unsubscribe for signals on given path.

        :param path: SHV path previously passed to :func:`subscribe`.
        :return: ``True`` in case such subscribe was located and ``False`` otherwise.
        """
        resp = await self.call(
            ".app/broker/currentClient" if await self._peer_is_shv3() else ".broker/app",
            "unsubscribe",
            {"method": "chng", "path": path},
        )
        assert is_shvbool(resp)
        return bool(resp)

    async def _peer_is_shv3(self) -> bool:
        """Check if peer supports at least SHV 0.1."""
        if self.__peer_is_shv3 is None:
            try:
                major = await self.call(".app", "shvVersionMajor")
                self.__peer_is_shv3 = isinstance(major, int) and major >= 0
            except RpcError:
                self.__peer_is_shv3 = False
        return self.__peer_is_shv3

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
        if method == "ls":
            return self._method_call_ls(path, params)
        if method == "dir":
            return self._method_call_dir(path, params)
        if path == ".app":
            if method == "shvVersionMajor":
                return SHV_VERSION_MAJOR
            if method == "shvVersionMinor":
                return SHV_VERSION_MINOR
            if method == "appName":
                return self.APP_NAME
            if method == "appVersion":
                return self.APP_VERSION
            if method == "ping":
                return None
        raise RpcMethodNotFoundError(
            f"No such path '{path}' or method '{method}' or access rights."
        )

    def _method_call_ls(self, path: str, params: SHVType) -> SHVType:
        """Implementation of ``ls`` method call."""
        # TODO list is backward compatibility
        if is_shvnull(params) or isinstance(params, list):
            res = []
            for v in self._ls(path):
                if v not in res:
                    res.append(v)
            if not res and not self._valid_path(path):
                raise RpcMethodNotFoundError(f"No such node: {path}")
            return res
        if isinstance(params, str):
            return any(v == params for v in self._ls(path))
        raise RpcInvalidParamsError("Use Null or String with node name")

    def _ls(self, path: str) -> typing.Iterator[str]:
        """Implement ``ls`` method for all nodes.

        The default implementation supports `.app` path. Your implementation
        should yield child nodes.

        Always call this as first before you yield your own methods to provide
        users with standard nodes.

        :param path: SHV path that should be listed.
        :return: Iterator over child nodes of the node on the path.
        """
        if not path:
            yield ".app"

    def _valid_path(self, path: str) -> bool:
        """Check that :meth:`_ls` reports this path as existing.

        :param path: SHV path to be validated.
        :return: ``True`` if :meth:`_ls` on parent node reports node with this tail
            piece. ``False`` is returned otherwise.
        """
        if not path:
            return True  # The root path always exists
        if "/" in path:
            index = path.rindex("/")
            return any(path[index + 1 :] == v for v in self._ls(path[:index]))
        return any(path == v for v in self._ls(""))

    def _method_call_dir(self, path: str, params: SHVType) -> SHVType:
        """Implementation of ``dir`` method call."""
        if not self._valid_path(path):
            raise RpcMethodNotFoundError(f"No such node: {path}")
        if is_shvnull(params) or isinstance(params, list):
            return list(d.tomap() for d in self._dir(path))
        if isinstance(params, str):
            for d in self._dir(path):
                if d.name == params:
                    return d.tomap()
            return None
        raise RpcInvalidParamsError("Use Null or String with node name")

    def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
        """Implement ``dir`` method for all nodes.

        This implementation is called only for valid paths (:meth:`_valid_path`).

        Always call this as first before you yield your own methods to provide
        users with standard ones.

        :param path: SHV path method should be listed for.
        :return: List of methods associated with given node.
        """
        yield RpcMethodDesc("dir", RpcMethodSignature.RET_PARAM)
        yield RpcMethodDesc("ls", RpcMethodSignature.RET_PARAM)
        if path == ".app":
            yield RpcMethodDesc.getter("shvVersionMajor", RpcMethodAccess.BROWSE)
            yield RpcMethodDesc.getter("shvVersionMinor", RpcMethodAccess.BROWSE)
            yield RpcMethodDesc.getter("appName", RpcMethodAccess.BROWSE)
            yield RpcMethodDesc.getter("appVersion", RpcMethodAccess.BROWSE)
            yield RpcMethodDesc("ping", RpcMethodSignature.VOID_VOID)

    async def _value_update(self, path: str, value: SHVType) -> None:
        """Handle value change (`chng` method)."""
