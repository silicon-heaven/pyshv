"""RPC Client connection to some SHV broker."""
import asyncio
import datetime
import logging
import typing
import collections.abc

from .rpcclient import RpcClient, get_next_rpc_request_id
from .rpcmessage import RpcMessage
from .value import SHVType, shvmeta

logger = logging.getLogger(__name__)


class ClientConnection:
    """Connection to some SHV RPC broker.

    Compared to the plain `RpcClient` this provides loop that handles messages
    received from the broker. It is designed to connect to the broker as it
    provides methods with common tasks performed on or trough SHV broker.
    """

    def __init__(self) -> None:
        self.rpc_client: RpcClient | None = None
        self._receiver_task: asyncio.Task | None = None
        self._signal_handlers: dict[str, typing.Any] = {}
        self._response_events: dict[int, asyncio.Event] = {}
        self._response_messages: dict[int, RpcMessage] = {}

    async def connect(
        self,
        host: str | None,
        port: int = 3755,
        user: str | None = None,
        password: str | None = None,
        login_type: RpcClient.LoginType = RpcClient.LoginType.SHA1,
    ) -> None:
        """Connect and login to the SHV broker (currently only TCP).

        :param host: IP/Hostname
        :param port: Port to connect to
        :param user: User name used to login
        :param password: Password used to login
        :param login_type: Type of the login to be used
        :raises RuntimeError: in case connection is already established
        """
        if self._receiver_task is not None:
            raise RuntimeError("Can't connect, client already connected")
        self.rpc_client = await RpcClient.connect(host, port)
        await self.rpc_client.login(user=user, password=password, login_type=login_type)
        self.rpc_client.callback = self._handle_msg
        self._receiver_task = asyncio.create_task(self.rpc_client.read_loop())

    async def disconnect(self) -> None:
        """Disconnect an existing connection.

        The call to the disconnect when client is not connected is silently
        ignored.
        """
        if self._receiver_task is None:
            return
        self._receiver_task.cancel()
        self.rpc_client = None
        self._receiver_task = None

    async def call_shv_method_blocking(
        self, shv_path: str, method: str, params: typing.Any = None
    ) -> RpcMessage:
        """Call given method wait for result.

        :param shv_path: path to the node with requested method
        :param method: name of the method to call
        :param params: optional parameters passed to the call
        :returns: reponse from the called method
        :raises RuntimeError: in case client is not connected
        """
        if self.rpc_client is None or self._receiver_task is None:
            raise RuntimeError("Client not connected")
        req_id = get_next_rpc_request_id()
        response_event = asyncio.Event()
        self._response_events[req_id] = response_event
        await self.rpc_client.call_shv_method_with_id(req_id, shv_path, method, params)
        await response_event.wait()
        return self._response_messages.pop(req_id)

    def set_value_change_handler(self, shv_path: str, handler: typing.Callable) -> None:
        """Register given handler to be called on received signal.

        :param shv_path: Path to the node harler should be called for. You can
            use shorter path but only handler with most exact match is called.
        :param handler: Function to be called when signal is received
        """
        logger.debug("Setting signal handler for path: %s", shv_path)
        self._signal_handlers[shv_path] = handler

    def clear_value_change_handler(self, shv_path: str):
        """Remove previously registered handler with set_value_change_handler.

        :param shv_path: Exactly the same string that was used to register
            handler previously.
        :raises KeyError: in case there was no such registration previously.
        """

    async def subscribe_path(self, shv_path: str) -> None:
        """Subscribe to the changes on the given SHV path.

        :param shv_path: SHV path to subscribe on
        :raises RuntimeError: when subscribe fails for any reason
        """
        resp = await self.call_shv_method_blocking(".broker/app", "subscribe", shv_path)
        if not resp.result():
            # TODO this is weird pattern. Just add handler as part of the
            # subscribe and allow changing handler trough this method
            self._signal_handlers.pop(shv_path)
            raise RuntimeError(f"Subscription for {shv_path} failed: {resp.error()}")

    async def get_snapshot_and_update(self, shv_home: str) -> None:
        """Get snapshot of the logs and trigger change handlers.

        Use this to receive old values.

        :param shv_home: SHV path to the home of the device where getLog method
            is available.
        """
        params = {
            "recordCountLimit": 10000,
            "withPathsDict": True,
            "withSnapshot": True,
            "withTypeInfo": False,
            "since": datetime.datetime.now(),
        }
        resp = await self.call_shv_method_blocking(shv_home, "getLog", params)
        result: SHVType = resp.result()
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
                    path = paths_dict[idx]
                    if not isinstance(path, str):
                        continue
                    # print(f'idx: {idx}, path: {path}, val: {value}')
                    self.update_value_for_path(path, value)

    def update_value_for_path(self, path: str, value: typing.Any) -> None:
        """Call value change handler for the given path with the given value.

        :param path: SHV path for the changed value
        :param value: The new value (after change)
        """
        handler = self._get_signal_handler(path)
        if handler is not None:
            handler(path, value)

    async def _handle_msg(self, _: RpcClient, msg: RpcMessage) -> None:
        """Handle received message."""
        if msg.is_response():
            req_id = msg.request_id()
            if req_id in self._response_events:
                self._response_messages[req_id] = msg
                event = self._response_events.pop(req_id)
                event.set()
        elif msg.is_signal():
            method = msg.method()
            path = msg.shv_path() or ""
            if method == "chng":
                handler = self._get_signal_handler(path)
                if handler is not None:
                    asyncio.get_event_loop().call_soon(handler, path, msg.params())

    def _get_signal_handler(self, shv_path: str) -> None | typing.Callable:
        """Get the handler for the longest path match."""
        split_key = shv_path.split("/")
        paths = (
            "/".join(split_key[: len(split_key) - i]) for i in range(len(split_key))
        )
        return next(
            (
                self._signal_handlers[path]
                for path in paths
                if path in self._signal_handlers
            ),
            None,
        )
