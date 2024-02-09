"""The base for the various high level SHV RPC interfaces."""
import asyncio
import collections.abc
import contextlib
import logging
import traceback
import typing

from .__version__ import __version__
from .rpcclient import RpcClient
from .rpcerrors import (
    RpcError,
    RpcInvalidParamsError,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
)
from .rpcmessage import RpcMessage
from .rpcmethod import RpcMethodAccess, RpcMethodDesc
from .shvversion import SHV_VERSION_MAJOR, SHV_VERSION_MINOR
from .value import SHVType, is_shvbool, is_shvnull

logger = logging.getLogger(__name__)


class SimpleBase:
    """SHV RPC made simple to use.

    You want to use this if you plan to implement your own specific RPC handler
    but in most cases you might want to use :class:`SimpleClient` or
    :class:`SimpleDevice` instead.

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
    APP_VERSION: str = __version__
    """Version of the application reported to the SHV.

    You should change this value in child class to report a correct number.
    """

    def __init__(
        self,
        client: RpcClient,
        call_attempts: int = 1,
        call_timeout: float | None = 300.0,
    ):
        self.client = client
        """The underlaying RPC client instance."""
        self.task = asyncio.create_task(self._loop())
        """Task running the message handling loop."""
        self.call_attempts = call_attempts
        """Number of attempts when no response is received before call is abandoned.
        You can use zero or negative number to have unlimited attempts.
        """
        self.call_timeout = call_timeout
        """Timeout in seconds before call is attempted again or abandoned."""
        self._calls_event: dict[int, asyncio.Event] = {}
        self._calls_msg: dict[int, RpcMessage] = {}
        self.__peer_is_shv3: None | bool = None

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
        with contextlib.suppress(EOFError):
            while msg := await self.client.receive(raise_error=False):
                if msg is RpcClient.Control.RESET:
                    self._reset()
                else:
                    asyncio.create_task(self._message(msg))

    async def _send(self, msg: RpcMessage) -> None:
        """Send message.

        :class:`SimpleBase` implementation should be using this method instead
        of ``self.client.send`` to ensure that send can be correctly overwritten
        and optionally postponed or blocked by child implementations.
        """
        await self.client.send(msg)

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
            await self._send(resp)
        elif msg.is_response:
            rid = msg.request_id
            assert rid is not None
            if rid in self._calls_event:
                self._calls_msg[rid] = msg
                self._calls_event.pop(rid).set()
        elif msg.is_signal:
            if msg.method == "chng":
                await self._value_update(msg.path, msg.param)

    def _reset(self) -> None:
        """Handle peer's reset request."""
        logger.info("Doing reset")
        for event in self._calls_event.values():
            event.set()

    async def reset(self) -> None:
        """Reset the client and connection.

        This calls :meth:`RpcClient.reset` as well as reset of the internal
        state.
        """
        await self.client.reset()
        self._reset()

    async def call(
        self,
        path: str,
        method: str,
        param: SHVType = None,
        call_attempts: int | None = None,
        call_timeout: float | None = None,
    ) -> SHVType:
        """Call given method on given path with given parameter.

        Note that this is coroutine and thus it is up to you if you await it or
        use asyncio tasks.

        The delivery of the messages is not ensure in SHV network (they can be
        dropped due to multiple reasons without informing the source of the
        message) and thus this method can attempt the request sending multiple
        times if it doesn't receive an appropriate response.

        :param path: SHV path method is associated with.
        :param method: SHV method name to be called.
        :param param: Parameter passed to the called method.
        :param call_attempts: Allows override of the object setting.
        :param call_timeout: Allows override of the object setting.
        :return: Return value on successful method call.
        :raise RpcError: The call result in error that is propagated by raising
            `RpcError` or its children based on the failure.
        :raise TimeoutError: when response is not received before timeout with
            all attempts depleted.
        :raise EOFError: when client disconnected and thus request can't be sent
          or response received.
        """
        call_attempts = self.call_attempts if call_attempts is None else call_attempts
        call_timeout = self.call_timeout if call_timeout is None else call_timeout
        msg = RpcMessage.request(path, method, param)
        rid = msg.request_id
        event = asyncio.Event()
        self._calls_event[rid] = event
        attempt = 0
        while call_attempts < 1 or attempt < call_attempts:
            attempt += 1
            await self._send(msg)
            try:
                async with asyncio.timeout(call_timeout):
                    await event.wait()
            except TimeoutError:
                continue
            if rid not in self._calls_msg:
                self._calls_event[rid].clear()
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

        Note that this is coroutine and thus it is up to you if you await it or
        use asyncio tasks.

        :param path: SHV path method is associated with.
        :param method: SHV method name to be called.
        :param param: Parameter that is the signaled value.
        :param access: Minimal access level needed to get the signal.
        """
        await self._send(RpcMessage.signal(path, method, param, access))

    async def ping(self) -> None:
        """Ping the peer to check the connection."""
        await self.call(
            ".app" if await self._peer_is_shv3() else ".broker/currentClient",
            "ping",
        )

    async def ls(self, path: str) -> list[str]:
        """List child nodes of the node on the specified path.

        :param path: SHV path to the node we want children to be listed for.
        :return: list of child nodes.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "ls")
        if not isinstance(res, list):  # pragma: no cover
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
        if not isinstance(res, bool):  # pragma: no cover
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
        if isinstance(res, list):  # pragma: no cover
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
        if isinstance(res, list):  # pragma: no cover, backward compatibility
            res = res[0] if len(res) == 1 else None
        if is_shvnull(res):
            return None
        return RpcMethodDesc.fromshv(res)

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
        :return: ``True`` if :meth:`_ls` on parent node reports node with this
          tail piece. ``False`` is returned otherwise.
        """
        if not path:
            return True  # The root path always exists
        if "/" in path:
            index = path.rindex("/")
            return any(path[index + 1 :] == v for v in self._ls(path[:index]))
        return any(path == v for v in self._ls(""))

    def _method_call_dir(self, path: str, param: SHVType) -> SHVType:
        """Implement ``dir`` method call functionality."""
        if not self._valid_path(path):
            raise RpcMethodNotFoundError(f"No such node: {path}")
        # Note: The list here is backward compatibility
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
