"""The base for the various high level SHV RPC interfaces."""

from __future__ import annotations

import asyncio
import collections
import collections.abc
import contextlib
import datetime
import functools
import logging
import time

from .__version__ import VERSION
from .path import SHVPath
from .rpcaccess import RpcAccess
from .rpcdir import RpcDir
from .rpcerrors import (
    RpcError,
    RpcInvalidParamError,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
    RpcRequestInvalidError,
    RpcTryAgainLaterError,
    RpcUserIDRequiredError,
)
from .rpcmessage import RpcMessage
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

    :param client: The RPC client instance to wrap and manage.
    :param call_timeout: Timeout in seconds before call is abandoned. The
      default is no timeout and thus infinite waiting. This is handy if you
      don't want to wrap call calls in your code with :func:`asyncio.timeout`
      and does exactly the same thing.
    :param call_query_timeout: Timeout in seconds before query is used to check
      the request status. The shorter time will cause faster message lost
      detection while the longer
    :param call_retry_timeout: Timeout in seconds when the request is sent
      again if there is no response received from the device.
    :param user_id: The default user ID to be used.
    :param peer_shv_version: The assumed SHV version of the peer. In default
      the exact version is detected but sometimes it is desirable to skip this
      check of enforce a different version for testing purposes.
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
    """

    def __init__(
        self,
        client: RpcClient,
        call_query_timeout: float = 1.0,
        call_retry_timeout: float = 60.0,
        user_id: str = "",
        peer_shv_version: tuple[int, int] | None = None,
    ) -> None:
        self.client = client
        """The underlining RPC client instance.

        **Do not send messages by directly accessing this property. You must use
        implementations provided by this class!**
        """
        self.task = asyncio.create_task(self._loop())
        """Task running the message handling receive loop."""
        self.user_id = user_id
        """The default user ID provided if method should be requested with it."""
        self.call_query_timeout = call_query_timeout
        """Timeout in seconds before :meth:`call` queries the state of the request."""
        self.call_retry_timeout = call_retry_timeout
        """Timeout in seconds before :meth:`call` send request again.

        Be aware how this interacts with :attr:`SHVBase.call_query_timeout`.
        This should be longer to ensure that we try to query the request before
        it is submitted as the whole again.

        This timeout is applied only if we get no response for given amount of
        time. Any response on query on voluntary one extends this timeout.
        """
        self._requests: dict[tuple[int, ...], tuple[asyncio.Task, SHVBase.Request]] = {}
        self._responses: dict[int, asyncio.Queue[RpcMessage | None]] = {}
        self._peer_shv_version = peer_shv_version
        self.__initial_peer_shv_version = peer_shv_version
        self.__send_semaphore = asyncio.Semaphore()
        self.__send_queue: collections.deque[tuple[RpcMessage, asyncio.Future]]
        self.__send_queue = collections.deque()

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
        send_task = asyncio.create_task(self._send_loop())
        try:
            with contextlib.suppress(EOFError):
                while msg := await self.client.receive():
                    if msg is RpcClient.Control.RESET:
                        self._reset()
                    elif msg.is_valid():
                        await self._message(msg)
                    else:
                        logger.info("%s: Dropped invalid message: %s", self.client, msg)
        finally:
            send_task.cancel()
            tasks = [send_task]
            for request_task, _ in self._requests.values():
                request_task.cancel()
                tasks.append(request_task)
            res = await asyncio.gather(*tasks, return_exceptions=True)
            if excs := [
                v
                for v in res
                if isinstance(v, BaseException)
                and not isinstance(v, asyncio.CancelledError)
            ]:
                if len(excs) == 1:
                    raise excs[0]
                raise BaseExceptionGroup("Collected errors from SHVBase", excs)

    def _reset(self) -> None:
        """Handle peer's reset request."""
        logger.info("%s: Doing reset", self.client)
        self._peer_shv_version = self.__initial_peer_shv_version
        for request_task, _ in self._requests.values():
            request_task.cancel()
        for queue in self._responses.values():
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    async def reset(self) -> None:
        """Reset the client and connection.

        This calls :meth:`RpcClient.reset` as well as reset of the internal
        state.
        """
        await self.client.reset()
        self._reset()

    async def call(
        self,
        path: str | SHVPath,
        method: str,
        param: SHVType = None,
        user_id: str | None = None,
        query_timeout: float | None = None,
        retry_timeout: float | None = None,
        progress: collections.abc.Callable[
            [float | None], collections.abc.Awaitable[None] | None
        ]
        | None = None,
    ) -> SHVType:
        """Call given method on given path with given parameter.

        Note that this is coroutine and thus it is up to you if you await it or
        use asyncio tasks. You can also freely use :func:`asyncio.timeout` to
        timeout the call.

        The delivery of the messages is not ensure in SHV network (they can be
        dropped due to multiple reasons without informing the source of the
        message) and thus this method can send the request message multiple
        times if it doesn't receive an appropriate response.

        :param path: SHV path method is associated with.
        :param method: SHV method name to be called.
        :param param: Parameter passed to the called method.
        :param user_id: UserID added to the method call request. This is required
          by some RPC methods to identify the user and they will respond with
          :class:`RpcUserIDRequiredError` if it is missing. This is caught by
          this method and request will be attempted again with User ID ``""``.
          If you know that method needs User ID then you can prevent this round
          trip by setting this argument to ``""``. On the other hand sending
          all requests with User ID wastes with bandwidth. In general usage you
          should use :attr:`SHVBase.user_id` instead of just ``""`` to use the
          object default.
        :param query_timeout: Override :attr:`SHVBase.call_query_timeout` just
          for this one call.
        :param retry_timeout: Override :attr:`SHVBase.call_retry_timeout` just
          for this one call.
        :param progress: An optional callback function that is called to report
          on progress of the call. It can be either function of coroutine. The
          argument passed is the float between 0 and 1 providing the progress
          signalization or ``None`` to signal that
          :class:`RpcTryAgainLaterError` was received. If you need to pass
          additional arguments to the function then use
          :func:`functools.partial`.
        :return: Return value on successful method call.
        :raise RpcError: The call result in error that is propagated by raising
          `RpcError` or its children based on the failure.
        :raise EOFError: when client disconnected and thus request can't be
          sent or response received.
        """
        query_timeout = (
            self.call_query_timeout if query_timeout is None else query_timeout
        )
        retry_timeout = (
            self.call_retry_timeout if retry_timeout is None else retry_timeout
        )

        async def callback_progress(value: float | None) -> None:
            if progress is not None:
                if (ares := progress(value)) is not None:
                    await ares

        request = RpcMessage.request(path, method, param, user_id=user_id)
        assert request.request_id not in self._responses
        queue = self._responses[request.request_id] = asyncio.Queue()
        try:
            while True:
                await self._send(request)
                last = time.monotonic()
                while True:
                    try:
                        tm = min(query_timeout, retry_timeout + last - time.monotonic())
                        async with asyncio.timeout(tm):
                            msg = await queue.get()
                        if msg is None:  # The communication reset
                            break  # We need to send request again
                        match msg.type:
                            case RpcMessage.Type.RESPONSE:
                                return msg.result
                            case RpcMessage.Type.RESPONSE_ERROR:
                                match msg.error:
                                    case RpcUserIDRequiredError():
                                        request.user_id = self.user_id
                                        rid = request.new_request_id()
                                        self._responses[rid] = queue
                                    case RpcRequestInvalidError():
                                        self._responses[request.request_id] = queue
                                    case RpcTryAgainLaterError():
                                        await callback_progress(None)
                                        rid = request.new_request_id()
                                        self._responses[rid] = queue
                                        tm = retry_timeout + last - time.monotonic()
                                        if tm > 0:
                                            await asyncio.sleep(tm)
                                    case error:
                                        raise error
                                break
                            case RpcMessage.Type.RESPONSE_DELAY:
                                await callback_progress(msg.delay)
                                last = time.monotonic()
                            case _:  # pragma: no cover
                                raise AssertionError(f"Invalid message: {msg}")
                    except TimeoutError:
                        if time.monotonic() - last > retry_timeout:
                            break
                        await self._send(request.make_abort(False))
        finally:
            if request.request_id in self._responses:
                if self.client.connected:
                    # TODO possibly put to the task
                    await self._send(request.make_abort(True))
                del self._responses[request.request_id]

    async def ping(self) -> None:
        """Ping the peer to check the connection."""
        await self.call(
            ".app" if await self.peer_shv_version() >= (3, 0) else ".broker/app", "ping"
        )

    async def ls(self, path: str | SHVPath) -> list[str]:
        """List child nodes of the node on the specified path.

        :param path: SHV path to the node we want children to be listed for.
        :return: list of child nodes.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "ls")
        if not isinstance(res, list):  # pragma: no cover
            raise RpcMethodCallExceptionError(f"Invalid result returned: {res!r}")
        return res

    async def ls_has_child(self, path: str | SHVPath, name: str) -> bool:
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

    async def dir(self, path: str | SHVPath, details: bool = False) -> list[RpcDir]:
        """List methods associated with node on the specified path.

        :param path: SHV path to the node we want methods to be listed for.
        :param details: If detailed listing should be performed instead of standard one.
        :return: list of the node's methods.
        :raise RpcMethodNotFoundError: when there is no such path.
        """
        res = await self.call(path, "dir", True if details else None)
        if isinstance(res, list):  # pragma: no cover
            return [RpcDir.from_shv(m) for m in res]
        raise RpcMethodCallExceptionError(f"Invalid result returned: {res!r}")

    async def dir_exists(self, path: str | SHVPath, name: str) -> bool:
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

    async def peer_shv_version(self) -> tuple[int, int]:
        """Get the peer's SHV version."""
        if self._peer_shv_version is None:
            self._peer_shv_version = (0, 0)
            with contextlib.suppress(RpcError):
                major = await self.call(".app", "shvVersionMajor")
                minor = await self.call(".app", "shvVersionMinor")
                if isinstance(major, int) and isinstance(minor, int):
                    self._peer_shv_version = (major, minor)
        return self._peer_shv_version

    async def _send_loop(self) -> None:
        """Loop used to send messages.

        We have a dedicated loop to send messages to identify if there is an
        empty bandwidth. Simply if there are no messages to be sent through
        :meth:`_send` then we can use :meth:`_idle_message` to generate idle
        messages.
        """
        while True:
            await self.__send_semaphore.acquire()
            if self.__send_queue:
                msg, future = self.__send_queue.popleft()
            else:
                res = self._idle_message()
                if res is None:
                    continue
                msg, future = res, None
            try:
                await self.client.send(msg)
            except Exception as exc:
                if future is None:
                    logger.warning("Idle send failed", exc_info=exc)
                else:
                    future.set_exception(exc)
            else:
                if future is not None:
                    future.set_result(None)

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
        future = asyncio.get_running_loop().create_future()
        self.__send_queue.append((msg, future))
        self.__send_semaphore.release()
        await future

    def _idle_message(self) -> RpcMessage | None:
        """Messages to be sent when there is bandwidth for them.

        In general we just try to propagate all messages but some of the
        messages might not have to be sent if we don't have bandwidth for them
        at the moment. These are commonly messages not directly requested by
        other side such as signals or some of the delayed responses.
        """
        for _, request in self._requests.values():
            if request._progress_dirty:
                request._progress_dirty = False
                return request._msg.make_response_delay(request._progress)
        return None

    def _idle_message_ready(self) -> None:
        """Notify internal implementation that idle message could be generated."""
        self.__send_semaphore.release()

    async def _message(self, msg: RpcMessage) -> None:
        """Handle every received message.

        :param msg: Received message.
        """
        match msg.type:
            case RpcMessage.Type.REQUEST:
                key = (msg.request_id, *msg.caller_ids)
                task = asyncio.create_task(self.__method_call(msg))
                self._requests[key] = (task, self.Request(msg, self))
                task.add_done_callback(functools.partial(self._requests.pop, key))
            case RpcMessage.Type.REQUEST_ABORT:
                await self.__method_call(msg)
            case RpcMessage.Type.RESPONSE | RpcMessage.Type.RESPONSE_ERROR:
                if (queue := self._responses.pop(msg.request_id, None)) is not None:
                    await queue.put(msg)
            case RpcMessage.Type.RESPONSE_DELAY:
                if (queue := self._responses.get(msg.request_id)) is not None:
                    await queue.put(msg)
            case RpcMessage.Type.SIGNAL:
                await self._got_signal(self.Signal(msg))

    async def __method_call(self, msg: RpcMessage) -> None:
        try:
            key = (msg.request_id, *msg.caller_ids)
            if msg.type == RpcMessage.Type.REQUEST:
                resp = msg.make_response()
                try:
                    resp.result = await self._method_call(self._requests[key][1])
                except Exception as exc:
                    resp.error = RpcError.from_exception(exc)
            elif key in self._requests and not msg.abort:
                resp = msg.make_response_delay(self._requests[key][1].progress)
            else:
                resp = msg.make_response()
                if key in self._requests:
                    self._requests[key][0].cancel()
                    resp.error = RpcRequestInvalidError("Request cancelled")
                else:
                    resp.error = RpcRequestInvalidError("No such request")

            with contextlib.suppress(EOFError):  # No need to spam logs on disconnect
                await self._send(resp)
        except Exception as exc:
            logger.warning("%s: Failed to respond: %s", self.client, msg, exc_info=exc)

    async def _method_call(self, request: SHVBase.Request) -> SHVType:
        """Handle request.

        Be aware that :class:`asyncio.CancelledError` can be raised to abort
        the request.

        :param request: SHV RPC request message info.
        :return: result of the method call. To report error you should raise
            :exc:`RpcError`.
        """
        match request.path, request.method:
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
            case _, "ls":
                return self._method_call_ls(request.path, request.param)
            case _, "dir":
                return self._method_call_dir(request.path, request.param)
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

    def _dir(self, path: str) -> collections.abc.Iterator[RpcDir]:  # noqa: PLR6301
        """Implement ``dir`` method for all nodes.

        This implementation is called only for valid paths
        (:meth:`shv.SHVBase._valid_path`).

        Always call this as first before you yield your own methods to provide
        users with standard ones.

        :param path: SHV path method should be listed for.
        :return: List of methods associated with given node.
        """
        yield RpcDir.stddir()
        yield RpcDir.stdls()
        if path == ".app":
            yield RpcDir.getter("shvVersionMajor", "n", "i")
            yield RpcDir.getter("shvVersionMinor", "n", "i")
            yield RpcDir.getter("name", "n", "s")
            yield RpcDir.getter("version", "n", "s")
            yield RpcDir.getter("date", "n", "t")
            yield RpcDir("ping")

    async def _got_signal(self, signal: Signal) -> None:
        """Handle signal.

        :param signal: SHV path to the node the signal is associated with.
        """

    class Request:
        """Set of parameters passed to the :meth:`shv.SHVBase._method_call`.

        This is provided as one data class to allow easier method typing as
        well as ability to more freely add or remove info items.
        """

        def __init__(self, msg: RpcMessage, shvbase: SHVBase) -> None:
            assert msg.type is RpcMessage.Type.REQUEST
            self._msg = msg
            self._shvbase = shvbase
            self._progress = 0.0
            self._progress_dirty = False

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
        def access(self) -> RpcAccess:
            """Access level of the client specified in this request."""
            return self._msg.rpc_access or RpcAccess.BROWSE

        @property
        def user_id(self) -> str | None:
            """The user's ID collected as message was passed around.

            This can be ``None`` when request message contained no ID. You can raise
            :class:`RpcUserIDRequiredError` if you need it.
            """
            return self._msg.user_id

        @property
        def caller_ids(self) -> collections.abc.Sequence[int]:
            """The sequence of the IDs for the caller.

            This sequence uniquely identifies this caller for this
            application, thus it can be used to have unique context specific to
            the caller.
            """
            return self._msg.caller_ids

        @property
        def progress(self) -> float:
            """The progress signaled for this request."""
            return self._progress

        @progress.setter
        def progress(self, value: float) -> None:
            self._progress = value
            if not self._progress_dirty:
                self._progress_dirty = True
                self._shvbase._idle_message_ready()

    class Signal:
        """Set of parameters passed to the :meth:`SHVBase._got_signal`.

        This is provided as one data class to allow easier method typing as
        well as ability to more freely add or remove info items.
        """

        def __init__(self, msg: RpcMessage) -> None:
            assert msg.type is RpcMessage.Type.SIGNAL
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
        def access(self) -> RpcAccess:
            """Access level of the signal."""
            return self._msg.rpc_access or RpcAccess.READ

        @property
        def user_id(self) -> str | None:
            """User's ID recorded in the signal.

            This can be ``None`` when request message contained no ID.
            """
            return self._msg.user_id
