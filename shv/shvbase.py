"""The base for the various high level SHV RPC interfaces."""

from __future__ import annotations

import asyncio
import collections.abc
import contextlib
import datetime
import logging
import traceback

from .__version__ import VERSION
from .rpcerrors import (
    RpcError,
    RpcInvalidParamError,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
    RpcUserIDRequiredError,
)
from .rpcmessage import RpcMessage
from .rpcmethod import RpcMethodAccess, RpcMethodDesc
from .rpctransport import RpcClient
from .shvversion import SHV_VERSION_MAJOR, SHV_VERSION_MINOR
from .value import SHVType, is_shvbool, is_shvnull

logger = logging.getLogger(__name__)


class SHVBase:
    """SHV RPC object API base class.

    You want to use this if you plan to implement your own specific RPC message
    handler but in most cases you might want to use :class:`shv.SHVClient` or
    :class:`shv.SHVDevice` instead.

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
    APP_VERSION: str = VERSION
    """Version of the application reported to the SHV.

    You should change this value in child class to report a correct number.

    :param client: The RPC client instance to wrap and manage.
    :param call_attempts: Number of attempts for :meth:`call` when no response
      is received before call is abandoned. You can use zero (or negative
      number) for unlimited number of attempts. The default is a single attempt
      and this only regular one call.
    :param call_timeout: Timeout in seconds before call is attempted again or
      abandoned (if there was too much call attempts). This is time before we
      consider response to be lost.
    """

    def __init__(
        self,
        client: RpcClient,
        call_attempts: int = 1,
        call_timeout: float | None = 300.0,
    ) -> None:
        self.client = client
        """The underlaying RPC client instance.

        **Do not send messages by directly accessing this property. You must use
        implementations provided by this class!**
        """
        self.task = asyncio.create_task(self._loop())
        """Task running the message handling receive loop."""
        self.call_attempts = call_attempts
        """Number of attempts when no response is received before call is abandoned.
        You can use zero for no  or negative number to have unlimited attempts.
        """
        self.call_timeout = call_timeout
        """Timeout in seconds before call is attempted again or abandoned."""
        self._calls_event: dict[int, asyncio.Event] = {}
        self._calls_msg: dict[int, RpcMessage] = {}
        self.__peer_is_shv3: bool | None = None

    async def disconnect(self) -> None:
        """Disconnect an existing connection.

        The call to the disconnect when client is not connected is silently
        ignored.

        Await blocks until disconnect is completed. You can use
        ``x.client.disconnect()`` to only initialize disconnect without waiting
        for it to take an effect.
        """
        self.client.disconnect()
        await self.task

    async def _loop(self) -> None:
        """Loop run in asyncio task to receive messages."""
        async with asyncio.TaskGroup() as tg:
            with contextlib.suppress(EOFError):
                while msg := await self.client.receive(raise_error=False):
                    if msg is RpcClient.Control.RESET:
                        self._reset()
                    elif msg.is_valid():
                        tg.create_task(self._message(msg))
                    else:
                        logger.info("%s: Dropped invalid message: %s", self.client, msg)

    def _reset(self) -> None:
        """Handle peer's reset request."""
        logger.info("%s: Doing reset", self.client)
        self.__peer_is_shv3 = None
        for event in self._calls_event.values():
            event.set()

    async def reset(self) -> None:
        """Reset the client and connection.

        This calls :meth:`RpcClient.reset` as well as reset of the internal
        state.
        """
        await self.client.reset()
        self._reset()

    async def _send(self, msg: RpcMessage) -> None:
        """Send message.

        You should be using this method instead of ``self.client.send`` to
        ensure that send can be correctly overwritten and optionally postponed
        or blocked by child implementations.

        This is intentionally marked as protected (accessible only by class and
        its children methods) because generic message must be send only for
        valid paths and methods and that is something only class itself can
        ensure. Your implemntation should provide public methods that protects
        against call with invalid path or method.

        Note that this is coroutine and thus it is up to you if you await it or
        use asyncio tasks.

        :param msg: The message to be send.
        """
        # TODO possibly lock to prevent from spliting this call
        await self.client.send(msg)

    async def call(
        self,
        path: str,
        method: str,
        param: SHVType = None,
        call_attempts: int | None = None,
        call_timeout: float | None = None,
        user_id: str | None = None,
    ) -> SHVType:
        """Call given method on given path with given parameter.

        Note that this is coroutine and thus it is up to you if you await it or
        use asyncio tasks.

        The delivery of the messages is not ensure in SHV network (they can be
        dropped due to multiple reasons without informing the source of the
        message) and thus this method can send the request message multiple
        times if it doesn't receive an appropriate response.

        :param path: SHV path method is associated with.
        :param method: SHV method name to be called.
        :param param: Parameter passed to the called method.
        :param call_attempts: Allows override of the object setting.
        :param call_timeout: Allows override of the object setting.
        :param user_id: UserID added to the method call request. This is required
          by some RPC methods to identify the user and they will respond with
          :class:`RpcUserIDRequiredError` if it is missing. This is caught by
          this method and request will be attempted again (not counting in
          ``call_attempts``) with User ID ``""``. If you know that method needs
          User ID then you can prevent this round trip by setting this argument
          to ``""``. On the other hand sending all requests with User ID wastes
          with bandwidth.
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
        request = RpcMessage.request(path, method, param, user_id=user_id)
        event = asyncio.Event()
        self._calls_event[request.request_id] = event
        attempt = 0
        while call_attempts < 1 or attempt < call_attempts:
            attempt += 1
            await self._send(request)
            try:
                async with asyncio.timeout(call_timeout):
                    await event.wait()
            except TimeoutError:
                continue
            if request.request_id not in self._calls_msg:
                self._calls_event[request.request_id].clear()
                continue
            response = self._calls_msg.pop(request.request_id)
            if response.is_error:
                rpc_error = response.rpc_error
                if not isinstance(rpc_error, RpcUserIDRequiredError):
                    raise response.rpc_error
                attempt -= 1  # Annul this attempt
                request.user_id = ""
                event.clear()
                self._calls_event[request.new_request_id()] = event
                continue
            return response.result
        raise TimeoutError

    async def ping(self) -> None:
        """Ping the peer to check the connection."""
        await self.call(".app" if await self.peer_is_shv3() else ".broker/app", "ping")

    async def ls(self, path: str) -> list[str]:
        """List child nodes of the node on the specified path.

        :param path: SHV path to the node we want children to be listed for.
        :return: list of child nodes.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "ls")
        if not isinstance(res, list):  # pragma: no cover
            raise RpcMethodCallExceptionError(f"Invalid result returned: {res!r}")
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
            raise RpcMethodCallExceptionError(f"Invalid result returned: {res!r}")
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
            return [RpcMethodDesc.from_shv(m) for m in res]
        raise RpcMethodCallExceptionError(f"Invalid result returned: {res!r}")

    async def dir_exists(self, path: str, name: str) -> bool:
        """Check if method exists using ``dir`` method.

        :param path: SHV path to the node we want methods to be listed for.
        :param name: Name of the method which existence should be checked.
        :return: ``True`` if method exists and ``False`` otherwise.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "dir", name)
        # list, null and mapping is backward compatibility
        if not isinstance(
            res, bool | collections.abc.Mapping | collections.abc.Sequence | None
        ):  # pragma: no cover
            raise RpcMethodCallExceptionError(f"Invalid result returned: {res!r}")
        return bool(res)

    async def peer_is_shv3(self) -> bool:
        """Check if peer supports at least SHV 3.0."""
        if self.__peer_is_shv3 is None:
            try:
                major = await self.call(".app", "shvVersionMajor")
                self.__peer_is_shv3 = isinstance(major, int) and major >= 0
            except RpcError:
                self.__peer_is_shv3 = False
        return self.__peer_is_shv3

    async def _message(self, msg: RpcMessage) -> None:
        """Handle every received message.

        :param msg: Received message.
        """
        if msg.is_request:
            resp = msg.make_response()
            try:
                resp.result = await self._method_call(self.Request(msg))
            except RpcError as exp:
                resp.rpc_error = exp
            except Exception as exc:
                resp.rpc_error = RpcMethodCallExceptionError(
                    "".join(traceback.format_exception(exc))
                )
            try:
                await self._send(resp)
            except EOFError:
                return  # No need to spam logs on disconnect
            except Exception as exc:
                logger.warning("%s: Failed to send response", self.client, exc_info=exc)
        elif msg.is_response:
            rid = msg.request_id
            if rid in self._calls_event:
                self._calls_msg[rid] = msg
                self._calls_event.pop(rid).set()
        elif msg.is_signal:
            await self._got_signal(self.Signal(msg))

    async def _method_call(self, request: SHVBase.Request) -> SHVType:
        """Handle request.

        :param request: SHV RPC request message info.
        :return: result of the method call. To report error you should raise
            :exc:`RpcError`.
        """
        match request.path, request.method:
            case _, "ls":
                return self._method_call_ls(request.path, request.param)
            case _, "dir":
                return self._method_call_dir(request.path, request.param)
            case ".app", "shvVersionMajor":
                return SHV_VERSION_MAJOR
            case ".app", "shvVersionMinor":
                return SHV_VERSION_MINOR
            case ".app", "name":
                return self.APP_NAME
            case ".app", "version":
                return self.APP_VERSION
            case ".app", "date":
                return datetime.datetime.now().astimezone()
            case ".app", "ping":
                return None
        raise RpcMethodNotFoundError(
            f"No such path '{request.path}' or method '{request.method}' or access rights."
        )

    def _method_call_ls(self, path: str, param: SHVType) -> SHVType:
        """Implement ``ls`` method call functionality."""
        if is_shvnull(param):
            res = []
            for v in self._ls(path):
                if v not in res:
                    res.append(v)
            if not res and not self._valid_path(path):
                raise RpcMethodNotFoundError(f"No such node: {path}")
            return res
        if isinstance(param, str):
            return any(v == param for v in self._ls(path))
        raise RpcInvalidParamError("Use Null or String with node name")

    def _ls(self, path: str) -> collections.abc.Iterator[str]:  # noqa: PLR6301
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

    @staticmethod
    def _ls_node_for_path(
        path: str,
        full_path: str | collections.abc.Iterator[str],
    ) -> collections.abc.Iterator[str]:
        """Help with :meth:`_ls` implementation.

        This is helper designed to be called from :meth:`_ls` and simplifies a
        common operation that is extraction of the node name from the full path.

        With this function you effectively can remove the code like this from
        your codebase::

            fpath = "some/path/to/the/node"
            path = f"{path}/" if path else ""
            if fpath.startswith(path):
                yield fpath[len(path) :].partition("/")[0]

        And replace it with just::

            yield from self._ls_node_for_path(path, "some/path/to/the/node")

        :param path: ``path`` parameter passed to :meth:`_ls`.
        :param full_path: Path or iterator over paths the node name should be
          extracted from.
        """
        if path:
            path = f"{path}/"
        for pth in (full_path,) if isinstance(full_path, str) else full_path:
            if pth.startswith(path):
                yield pth[len(path) :].partition("/")[0]

    def _valid_path(self, path: str) -> bool:
        """Check that :meth:`_ls` reports this path as existing.

        :param path: SHV path to be validated.
        :return: ``True`` if :meth:`_ls` on parent node reports node with this
          tail piece. ``False`` is returned otherwise.
        """
        if not path:
            return True  # The root path always exists
        root, _, name = path.rpartition("/")
        return any(name == v for v in self._ls(root))

    def _method_call_dir(self, path: str, param: SHVType) -> SHVType:
        """Implement ``dir`` method call functionality."""
        if not self._valid_path(path):
            raise RpcMethodNotFoundError(f"No such node: {path}")
        if is_shvnull(param) or is_shvbool(param):
            return list(d.to_shv(bool(param)) for d in self._dir(path))
        if isinstance(param, str):
            return any(v.name == param for v in self._dir(path))
        raise RpcInvalidParamError("Use Null or Bool or String with node name")

    def _dir(self, path: str) -> collections.abc.Iterator[RpcMethodDesc]:  # noqa: PLR6301
        """Implement ``dir`` method for all nodes.

        This implementation is called only for valid paths
        (:meth:`shv.SHVBase._valid_path`).

        Always call this as first before you yield your own methods to provide
        users with standard ones.

        :param path: SHV path method should be listed for.
        :return: List of methods associated with given node.
        """
        yield RpcMethodDesc.stddir()
        yield RpcMethodDesc.stdls()
        if path == ".app":
            yield RpcMethodDesc.getter("shvVersionMajor", "n", "i")
            yield RpcMethodDesc.getter("shvVersionMinor", "n", "i")
            yield RpcMethodDesc.getter("name", "n", "s")
            yield RpcMethodDesc.getter("version", "n", "s")
            yield RpcMethodDesc.getter("date", "n", "t")
            yield RpcMethodDesc("ping")

    async def _got_signal(self, signal: Signal) -> None:
        """Handle signal.

        :param signal: SHV path to the node the signal is associated with.
        """

    class Request:
        """Set of parameters passed to the :meth:`shv.SHVBase._method_call`.

        This is provided as one data class to allow easier method typing as
        well as ability to more freely add or remove info items.
        """

        def __init__(self, msg: RpcMessage) -> None:
            assert msg.is_request
            self._msg = msg

        @property
        def path(self) -> str:
            """SHV path to the node the method is associated with."""
            return self._msg.path

        @property
        def method(self) -> str:
            """SHV method name requested to be called."""
            return self._msg.method

        @property
        def param(self) -> SHVType:
            """Parameter provided for the method call."""
            return self._msg.param

        @property
        def access(self) -> RpcMethodAccess:
            """Access level of the client specified in this request."""
            return self._msg.rpc_access or RpcMethodAccess.BROWSE

        @property
        def user_id(self) -> str | None:
            """The user's ID collected as message was passed around.

            This can be ``None`` when request message contained no ID. You can raise
            :class:`RpcUserIDRequiredError` if you need it.
            """
            return self._msg.user_id

    class Signal:
        """Set of parameters passed to the :meth:`SHVBase._got_signal`.

        This is provided as one data class to allow easier method typing as
        well as ability to more freely add or remove info items.
        """

        def __init__(self, msg: RpcMessage) -> None:
            assert msg.is_signal
            self._msg = msg

        @property
        def path(self) -> str:
            """SHV path signal is associated with."""
            return self._msg.path

        @property
        def signal(self) -> str:
            """Signal name."""
            return self._msg.signal_name

        @property
        def source(self) -> str:
            """SHV method name signal is associated with."""
            return self._msg.source

        @property
        def param(self) -> SHVType:
            """Value caried by signal."""
            return self._msg.param

        @property
        def access(self) -> RpcMethodAccess:
            """Access level of the signal."""
            return self._msg.rpc_access or RpcMethodAccess.READ

        @property
        def user_id(self) -> str | None:
            """User's ID recorded in the signal.

            This can be ``None`` when request message contained no ID.
            """
            return self._msg.user_id
