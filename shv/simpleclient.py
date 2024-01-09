"""RPC client manager that provides facitility to simply connect to the broker."""
import asyncio
import collections.abc
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
from .rpclogin import rpclogin_url
from .rpcmessage import RpcMessage
from .rpcmethod import RpcMethodAccess, RpcMethodDesc
from .rpcsubscription import RpcSubscription
from .rpcurl import RpcUrl
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

    def __init__(
        self,
        client: RpcClient,
        call_attempts: int = 1,
        call_timeout: float | None = 300.0,
        idle_disconnect: bool = False,
    ):
        self.client = client
        """The underlaying RPC client instance."""
        self.task = asyncio.create_task(self._loop())
        """Task running the message handling loop."""
        self.call_attempts = call_attempts
        """Number of attempts when no response is received before call is abandoned."""
        self.call_timeout = call_timeout
        """Timeout in seconds before call is attempted again or abandoned."""
        self.idle_disconnect = idle_disconnect
        """If client should be disconnected on IDLE_TIMEOUT instead of ping."""
        self._calls_event: dict[int, asyncio.Event] = {}
        self._calls_msg: dict[int, RpcMessage] = {}
        self.__peer_is_shv3: None | bool = None

    # TODO solve type hinting in this method. It seems that right now it is not
    # possible to correctly type hint the args and kwargs to copy Self # params.
    # https://discuss.python.org/t/how-to-properly-hint-a-class-factory-with-paramspec/27941/3
    @classmethod
    async def connect(
        cls: type[typing.Self],
        url: RpcUrl,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> typing.Self:
        """Connect and login to the SHV broker.

        Any additional parameters after ``url`` are passed to class
        initialization.

        :param url: SHV RPC URL to the broker
        :return: Connected instance.
        """
        client = await connect_rpc_client(url)
        await rpclogin_url(client, url, {"idleWatchDogTimeOut": int(cls.IDLE_TIMEOUT)})
        return cls(client, *args, **kwargs)

    async def disconnect(self) -> None:
        """Disconnect an existing connection.

        The call to the disconnect when client is not connected is silently
        ignored.

        This call blocks until disconnect is completed. You can use
        ``x.client.disconnect()`` to only initialize disconnect without waiting
        for it to take an effect.
        """
        self.client.disconnect()
        await self.task

    async def _loop(self) -> None:
        """Loop run in asyncio task to receive messages."""
        activity_task = asyncio.create_task(self._activity_loop())
        try:
            while msg := await self.client.receive(raise_error=False):
                asyncio.create_task(self._message(msg))
        except EOFError:
            pass
        activity_task.cancel()
        try:
            await activity_task
        except asyncio.exceptions.CancelledError:
            pass

    async def _activity_loop(self) -> None:
        """Loop run alongside with :meth:`_loop`.

        It either sends pings to the other side or it disconnects other side when
        idling. The operation is based on :param:`idle_disconnect`.
        """
        while self.client.connected:
            if self.idle_disconnect:
                t = time.monotonic() - self.client.last_receive
                if t < self.IDLE_TIMEOUT:
                    await asyncio.sleep(self.IDLE_TIMEOUT - t)
                else:
                    await self.disconnect()
            else:
                t = time.monotonic() - self.client.last_send
                if t < (self.IDLE_TIMEOUT / 2):
                    await asyncio.sleep(self.IDLE_TIMEOUT / 2 - t)
                else:
                    await self.client.send(
                        RpcMessage.request(
                            ".app"
                            if await self._peer_is_shv3()
                            else ".broker/currentClient",
                            "ping",
                        )
                    )

    async def _message(self, msg: RpcMessage) -> None:
        """Handle every received message."""
        if msg.is_request:
            resp = msg.make_response()
            method = msg.method
            assert method  # is ensured by is_request but not detected by mypy
            try:
                resp.result = await self._method_call(
                    msg.path,
                    method,
                    msg.rpc_access or RpcMethodAccess.BROWSE,
                    msg.param,
                )
            except RpcError as exp:
                resp.rpc_error = exp
            except Exception as exc:
                resp.rpc_error = RpcMethodCallExceptionError(
                    "".join(traceback.format_exception(exc))
                )
            await self.client.send(resp)
        elif msg.is_response:
            rid = msg.request_id
            assert rid is not None
            if rid in self._calls_event:
                self._calls_msg[rid] = msg
                self._calls_event.pop(rid).set()
        elif msg.is_signal:
            if msg.method == "chng":
                await self._value_update(msg.path, msg.param)

    async def call(self, path: str, method: str, param: SHVType = None) -> SHVType:
        """Call given method on given path with given parameter.

        Note that this is coroutine and this it is up to you if you await it or
        use asyncio tasks.

        :param path: SHV path method is associated with.
        :param method: SHV method name to be called.
        :param param: Parameter passed to the called method.
        :return: Return value on successful method call.
        :raise RpcError: The call result in error that is propagated by raising
            `RpcError` or its children based on the failure.
        :raise TimeoutError: when response is not received before timeout with
            all attempts depleted.
        """
        msg = RpcMessage.request(path, method, param)
        rid = msg.request_id
        event = asyncio.Event()
        self._calls_event[rid] = event
        for _ in range(self.call_attempts):
            await self.client.send(msg)
            try:
                async with asyncio.timeout(self.call_timeout):
                    await event.wait()
            except TimeoutError:
                continue
            msg = self._calls_msg.pop(rid)
            if msg.is_error:
                raise msg.rpc_error
            return msg.result
        raise TimeoutError

    async def signal(
        self,
        path: str,
        method: str = "chng",
        param: SHVType = None,
        access: RpcMethodAccess = RpcMethodAccess.READ,
    ) -> None:
        """Send signal from given path and method and with given parameter.

        Note that this is coroutine and this it is up to you if you await it or
        use asyncio tasks.

        :param path: SHV path method is associated with.
        :param method: SHV method name to be called.
        :param param: Parameter that is the signaled value.
        :param access: Minimal access level needed to get the signal.
        """
        msg = RpcMessage.signal(path, method, param, access)
        await self.client.send(msg)

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

    async def dir(self, path: str, details: bool = False) -> list[RpcMethodDesc]:
        """List methods associated with node on the specified path.

        :param path: SHV path to the node we want methods to be listed for.
        :param details: If detailed listing should be performed instead of standard one.
        :return: list of the node's methods.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "dir", True if details else None)
        if isinstance(res, list):
            return [RpcMethodDesc.fromshv(m) for m in res]
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
        return RpcMethodDesc.fromshv(res)

    async def subscribe(self, sub: RpcSubscription) -> None:
        """Perform subscribe for signals on given path.

        Subscribe is always performed on the node itself as well as all its
        children.

        :param sub: SHV RPC subscription to be added.
        """
        await self.call(
            ".app/broker/currentClient"
            if await self._peer_is_shv3()
            else ".broker/app",
            "subscribe",
            sub.toSHV(),
        )

    async def unsubscribe(self, sub: RpcSubscription) -> bool:
        """Perform unsubscribe for signals on given path.

        :param sub: SHV RPC subscription to be removed.
        :return: ``True`` in case such subscribe was located and ``False`` otherwise.
        """
        resp = await self.call(
            ".app/broker/currentClient"
            if await self._peer_is_shv3()
            else ".broker/app",
            "unsubscribe",
            sub.toSHV(),
        )
        assert is_shvbool(resp)
        return bool(resp)

    async def _peer_is_shv3(self) -> bool:
        """Check if peer supports at least SHV 3.0."""
        if self.__peer_is_shv3 is None:
            try:
                major = await self.call(".app", "shvVersionMajor")
                self.__peer_is_shv3 = isinstance(major, int) and major >= 0
            except RpcError:
                self.__peer_is_shv3 = False
        return self.__peer_is_shv3

    async def _method_call(
        self, path: str, method: str, access: RpcMethodAccess, param: SHVType
    ) -> SHVType:
        """Handle request in the provided message.

        :param path: SHV path to the node the method is associated with.
        :param method: method requested to be called.
        :param access: access level of the client specified in the request.
        :param param: Parameter to be passed to the called method.
        :return: result of the method call. To report error you should raise
            :exc:`RpcError`.
        """
        if method == "ls":
            return self._method_call_ls(path, param)
        if method == "dir":
            return self._method_call_dir(path, param)
        if path == ".app":
            match method:
                case "shvVersionMajor":
                    return SHV_VERSION_MAJOR
                case "shvVersionMinor":
                    return SHV_VERSION_MINOR
                case "name":
                    return self.APP_NAME
                case "version":
                    return self.APP_VERSION
                case "ping":
                    return None
        raise RpcMethodNotFoundError(
            f"No such path '{path}' or method '{method}' or access rights."
        )

    def _method_call_ls(self, path: str, param: SHVType) -> SHVType:
        """Implement ``ls`` method call functionality."""
        # TODO list is backward compatibility
        if is_shvnull(param) or isinstance(param, list):
            res = []
            for v in self._ls(path):
                if v not in res:
                    res.append(v)
            if not res and not self._valid_path(path):
                raise RpcMethodNotFoundError(f"No such node: {path}")
            return res
        if isinstance(param, str):
            return any(v == param for v in self._ls(path))
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

    async def _lschng(
        self, path: str, nodes: collections.abc.Mapping[str, bool]
    ) -> None:
        """Report change in the ls method.

        This provides implementation for "lschng" signal that must be used when you are
        changing the nodes tree to signal clients about that. The argument specifies top
        level nodes added or removed (based on the mapping value).

        :param path: SHV path to the valid node which children were added or removed.
        :param nodes: Map where key is node name of the node that is top level node,
          that was either added (for value ``True``) or removed (for value ``False``).
        """
        await self.signal(path, "lschng", nodes, RpcMethodAccess.BROWSE)

    def _method_call_dir(self, path: str, param: SHVType) -> SHVType:
        """Implement ``dir`` method call functionality."""
        if not self._valid_path(path):
            raise RpcMethodNotFoundError(f"No such node: {path}")
        # TODO the list here is backward compatibility
        if is_shvnull(param) or is_shvbool(param) or isinstance(param, list):
            return list(d.toshv(bool(param)) for d in self._dir(path))
        if isinstance(param, str):
            for d in self._dir(path):
                if d.name == param:
                    return d.toshv()
            return None
        raise RpcInvalidParamsError("Use Null or Bool or String with node name")

    def _dir(self, path: str) -> typing.Iterator[RpcMethodDesc]:
        """Implement ``dir`` method for all nodes.

        This implementation is called only for valid paths (:meth:`_valid_path`).

        Always call this as first before you yield your own methods to provide
        users with standard ones.

        :param path: SHV path method should be listed for.
        :return: List of methods associated with given node.
        """
        yield RpcMethodDesc.stddir()
        yield RpcMethodDesc.stdls()
        yield RpcMethodDesc.stdlschng()
        if path == ".app":
            yield RpcMethodDesc.getter("shvVersionMajor", "Null", "Int")
            yield RpcMethodDesc.getter("shvVersionMinor", "Null", "Int")
            yield RpcMethodDesc.getter("name", "Null", "String")
            yield RpcMethodDesc.getter("version", "Null", "String")
            yield RpcMethodDesc("ping")

    async def _value_update(self, path: str, value: SHVType) -> None:
        """Handle value change (`chng` method)."""
