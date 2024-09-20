"""RPC client manager that provides facitility to simply connect to the broker."""

import asyncio
import collections.abc
import contextlib
import logging
import time
import typing

from .rpclogin import RpcLogin
from .rpcmessage import RpcMessage
from .rpcparam import shvgett
from .rpcri import rpcri_legacy_subscription
from .rpctransport import RpcClient, connect_rpc_client
from .rpcurl import RpcUrl
from .simplebase import SimpleBase
from .value import SHVType

logger = logging.getLogger(__name__)


class SimpleClient(SimpleBase):
    """SHV client made simple to use.

    You most likely want to use this client instead of using RpcClient directly.

    It is designed as a RPC peer that is connected to the SHV RPC Broker.
    """

    APP_NAME: str = "pyshv-client"

    def __init__(
        self,
        client: RpcClient,
        login: RpcLogin,
        *args: typing.Any,  # noqa ANN401
        reconnects: int = 1,
        **kwargs: typing.Any,  # noqa ANN401
    ) -> None:
        super().__init__(client, *args, **kwargs)
        self.login: RpcLogin = login
        """The login used for logging to the connected broker."""
        self.reconnects: int = reconnects
        """Number of attempted reconnects before giving up.

        Any negative number means no limit in reconnects, zero is for no
        reconnects (client must already be connected) and one for only initial
        connection.

        Reconnects are attepted with increased amount of time between them. This
        increase is capped on cca. 1 minute after six attempts. This doesn't
        include timeouts that are part of the reconnect process itself (such as
        timeout of network socket).

        This affects the real reconnect (when receive would raise
        :class:`EOFError`). The reset is handled automatically no matter this
        settings.
        """
        self._subscribes: set[str] = set()
        self._connected = asyncio.Event()
        self._login_task = asyncio.create_task(self._login())

    # TODO solve type hinting in this method. It seems that right now it is not
    # possible to correctly type hint the args and kwargs to copy Self # params.
    # https://discuss.python.org/t/how-to-properly-hint-a-class-factory-with-paramspec/27941/3
    @classmethod
    async def connect(
        cls: type[typing.Self],
        url: RpcUrl | str,
        *args: typing.Any,  # noqa ANN401
        **kwargs: typing.Any,  # noqa ANN401
    ) -> typing.Self:
        """Connect and login to the SHV broker.

        Any additional parameters after ``url`` are passed to class initialization.

        :param url: SHV RPC URL to the broker
        :return: Connected instance.
        """
        if isinstance(url, str):
            url = RpcUrl.parse(url)
        res = cls(await connect_rpc_client(url), url.login, *args, **kwargs)
        try:
            await res.wait_for_login()
        except Exception as exc:
            await res.disconnect()
            raise exc
        return res

    async def wait_for_login(self) -> None:
        """Wait for login completion.

        This also propagates any exception that we encounter during the login
        process.
        """
        while True:
            try:
                await self._login_task
                return
            except asyncio.CancelledError:
                pass

    async def disconnect(self) -> None:  # noqa: D102
        self.reconnects = 0
        await super().disconnect()

    async def _loop(self) -> None:
        reconnect_attempt = 0
        while self.reconnects < 0 or self.reconnects >= reconnect_attempt:
            if self.client.connected:
                reconnect_attempt = 0
                self._connected.set()
                activity_task = asyncio.create_task(self._activity_loop())
                await super()._loop()
                self.client.disconnect()  # write stays open so close it
                self._connected.clear()
                activity_task.cancel()
                with contextlib.suppress(asyncio.exceptions.CancelledError):
                    await activity_task
            else:
                try:
                    await self.client.reset()
                except Exception as exc:
                    timeout = max(60, 2**reconnect_attempt)
                    logger.info(
                        "%s: Connect failed (waiting %d secs): %s",
                        self.client,
                        timeout,
                        exc,
                    )
                    await asyncio.sleep(timeout)
                else:
                    self.__restart_login()
            reconnect_attempt += 1

    async def _activity_loop(self) -> None:
        """Loop run alongside with :meth:`_loop`. It sends pings to the other side."""
        while True:
            t = time.monotonic() - self.client.last_send
            if t < (self.IDLE_TIMEOUT / 2):
                await asyncio.sleep(self.IDLE_TIMEOUT / 2 - t)
            else:
                await self.ping()

    async def _send(self, msg: RpcMessage) -> None:
        await self._connected.wait()
        if not msg.is_request or msg.path or msg.method not in {"hello", "login"}:
            await self._login_task
        await super()._send(msg)

    def _reset(self) -> None:
        super()._reset()
        self.__restart_login()

    def __restart_login(self) -> None:
        if not self._login_task.done():
            self._login_task.cancel()
        self._login_task = asyncio.create_task(self._login())

    async def _login(self) -> None:
        """Login operation and all steps done to prepare or restore client.

        This includes subscribes restoration after connection reset.

        Be aware when you are overwriting this as this is running in the
        """
        res = await self.call("", "hello")
        nonce = shvgett(res, "nonce", str, "")
        await self.call(
            "",
            "login",
            self.login.to_shv(nonce, {"idleWatchDogTimeOut": int(self.IDLE_TIMEOUT)}),
        )
        # Restore subscriptions
        for ri in self._subscribes:
            await self.__subscribe(ri)

    async def call(  # noqa: D102
        self,
        path: str,
        method: str,
        param: SHVType = None,
        call_attempts: int | None = None,
        call_timeout: float | None = None,
        user_id: str | None = None,
    ) -> SHVType:
        timeout = self.call_timeout if call_timeout is None else call_timeout
        if timeout is not None:
            timeout *= self.call_attempts if call_attempts is None else call_attempts
        async with asyncio.timeout(timeout):
            while True:
                with contextlib.suppress(EOFError):
                    return await super().call(
                        path, method, param, call_attempts, call_timeout, user_id
                    )
                await asyncio.sleep(0)  # Let loop detect disconnect
                await self._connected.wait()

    async def subscribe(self, ri: str) -> bool:
        """Perform subscribe for signals on given path.

        Subscribe is always performed on the node itself as well as all its
        children.

        :param ri: SHV RPC RI for subscription to be added.
        """
        res = await self.__subscribe(ri)
        self._subscribes.add(ri)
        return res

    async def __subscribe(self, ri: str) -> bool:
        compat = not await self.peer_is_shv3()
        return bool(
            await self.call(
                ".broker/currentClient" if not compat else ".broker/app",
                "subscribe",
                ri if not compat else rpcri_legacy_subscription(ri),
            )
        )

    async def unsubscribe(self, ri: str) -> bool:
        """Perform unsubscribe for signals on given path.

        :param ri: SHV RPC RI for subscription to be removed.
        :return: ``True`` in case such subscribe was located and ``False``
          otherwise.
        """
        compat = not await self.peer_is_shv3()
        resp = bool(
            await self.call(
                ".broker/currentClient" if not compat else ".broker/app",
                "unsubscribe",
                ri if not compat else rpcri_legacy_subscription(ri),
            )
        )
        if resp:
            self._subscribes.remove(ri)
        return resp

    def subscriptions(self) -> collections.abc.Iterator[str]:
        """Iterate over all subscriptions.

        Note that this uses local subscription cache. It won't reach for the
        current set of subscriptions on the server. This in not be an issue in
        almost all cases because because servers allow subscription
        modifications only to the current client and you should always use
        :meth:`subscribe` and :meth:`unsubscribe` and in such case there should
        be no way this cache gets invalidated compared to the Broker.
        """
        yield from iter(self._subscribes)
