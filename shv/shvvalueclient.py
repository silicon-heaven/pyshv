"""Common extension for the :class:`SHVClient`."""

from __future__ import annotations

import asyncio
import collections.abc
import datetime
import logging
import time
import typing

from .rpcerrors import RpcMethodCallExceptionError, RpcMethodNotFoundError
from .rpcri import rpcri_match
from .shvbase import SHVBase
from .shvclient import SHVClient
from .value import SHVMapType, SHVType, shvmeta, shvmeta_eq

logger = logging.getLogger(__name__)


class SHVValueClient(SHVClient, collections.abc.Mapping):
    """SHV client made to track values of properties more easily.

    This tailors to the use case of tracking and accessing various values more
    easily. You need to subscribe to specific path and this class automatically
    provides you with cached latest value as received through signals or fetched
    from logs (logs fetching has to be performed explicitly) or with prop_get.

    To access subscribed value you can index this object with SHV path to it.
    """

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:  # noqa ANNN401
        super().__init__(*args, **kwargs)  # notype
        self._cache: dict[str, tuple[float, SHVType]] = {}
        self._handlers: dict[
            str, collections.abc.Callable[[SHVValueClient, str, SHVType], None]
        ] = {}
        self._futures: dict[str, list[asyncio.Future]] = {}

    def __getitem__(self, key: str) -> SHVType:
        return self._cache[key][1]

    def __iter__(self) -> collections.abc.Iterator[str]:
        return iter(self._cache.keys())

    def __len__(self) -> int:
        return len(self._cache)

    async def _got_signal(self, signal: SHVBase.Signal) -> None:
        """Handle signal.

        :param signal: SHV path to the node the signal is associated with.
        """
        if signal.signal.endswith("chng") and signal.source == "get":
            await self._value_update(signal.path, signal.param)

    async def _value_update(self, path: str, value: SHVType) -> None:
        """Handle value change (``*chng`` signal associated with ``get`` method)."""
        handler = self._get_handler(path)
        if handler is not None and not shvmeta_eq(self.get(path, None), value):
            handler(self, path, value)
        for future in self._futures.pop(path, []):
            future.set_result(value)
        if self.is_subscribed(path):
            # Theoretically we should get only paths we subscribed for but user might
            # invoke subscribe on its own which could break our cache logic and thus
            # just guard against it here.
            self._cache[path] = (time.time(), value)

    def _get_handler(
        self, path: str
    ) -> collections.abc.Callable[[SHVValueClient, str, SHVType], None] | None:
        """Get the handler for the longest path match."""
        split_key = path.split("/")
        paths = (
            "/".join(split_key[: len(split_key) - i]) for i in range(len(split_key) + 1)
        )
        return next(
            (self._handlers[path] for path in paths if path in self._handlers),
            None,
        )

    async def prop_get(self, path: str, max_age: float = 0.0) -> SHVType:
        """Get value from the property associated with the node on given path.

        This always calls get method compared to item access that is served only from
        cache.

        :param path: SHV path to the property node.
        :param max_age: is maximum age in seconds to be specified for the get. Nonzero
          value results in value to be served from cache anywhere along the way (thus not
          just local cache).
        :return: Value of the property node.
        """
        # Serve from cache if cache was updated not before max_age
        if path in self._cache and self._cache[path][0] + max_age >= time.time():
            return self._cache[path][1]
        value = await self.call(path, "get", max_age if int(max_age * 1000) else None)
        if self.get(path, max_age if max_age else None) != value:
            await self._value_update(path, value)
        return value

    async def prop_set(self, path: str, value: SHVType, update: bool = False) -> None:
        """Set value to the property associated with the node on given path.

        :param path: SHV path to the property node.
        :param value: Value to be set to the property node.
        :param update: If internal cache should be immediatelly updated. Otherwise you
            cache would be updated only with get or change signal.
        """
        await self.call(path, "set", value)
        if update:
            await self._value_update(path, value)

    async def prop_change_wait(
        self,
        path: str,
        value: SHVType = None,
        timeout: float | int | None = 5.0,  # noqa ASYNC109
        get_period: float = 1.0,
    ) -> SHVType:
        """Wait for property change.

        The wait is implemented by combination of pooling and waiting for the change
        signal. Pooling uses :meth:`prop_get` every ``get_period``. If you previously
        subscribed on this path (that includes its parent) then it will wait for signal,
        otherwise it will just sleep between get attempts.

        note:: This uses :meth:`on_change` internally and thus it might temporally (for
        this method execution time) replace your own callback.

        :param path: SHV path to the property node.
        :param value: The value we compare against. It is ignored for if we have this
            path in cache and is ``None``. Otherwise it is used to actually detect the
            change (if returned value is not equal to this one).
        :param timeout: How long we should wait for change. Pass ``None`` to wait
            infinitely.
        :param get_period: How often the pooling should be performed.
        """
        tasks: set[asyncio.Task] = {
            asyncio.create_task(
                self._prop_change_wait(
                    path,
                    self.get(path, None) if value is None else value,
                    get_period,
                )
            )
        }
        if self.is_subscribed(path):
            tasks.add(asyncio.create_task(self.wait_for_change(path)))
        done, pending = await asyncio.wait(
            tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in pending:
            try:
                await task
            except asyncio.CancelledError:
                pass
        if not done:
            raise TimeoutError
        return done.pop().result()  # type: ignore

    async def _prop_change_wait(
        self, path: str, value: SHVType, period: float
    ) -> SHVType:
        while True:
            v = await self.prop_get(path)
            if v != value:
                return v
            await asyncio.sleep(period)

    def on_change(
        self,
        path: str,
        callback: collections.abc.Callable[[SHVValueClient, str, SHVType], None] | None,
    ) -> None:
        """Register callback handler called when value change is reported.

        The handler is called right before value is updated and thus it is possible to
        access the old and new value is provided as an argument. Note that it is up to
        the device if this signal is sent really only on value change or if it is sent
        more often.

        The default implementation of handler lookup (:meth:`_get_handler`) is that the
        most matching callback path is selected and callback for it called. This way you
        can get all notifications delivered to a single handler if you use empty string
        as the path.

        :param path: SHV path to the node (includes its children) change is expected on.
        :param callback: Function called when change notification is received. You can
            pass ``None`` to remove any existing callback. Note that there can be only
            one callback registered for a single path and thus a different callback
            replaces the previous one.
        """
        if callback is None:
            self._handlers.pop(path)
        else:
            self._handlers[path] = callback

    async def wait_for_change(self, path: str) -> SHVType:
        """Provide a way to await for the future change signal.

        Compared to the :meth:`on_change` the path has to match exactly.

        :param path: SHV path to the node the change signal is expected on.
        :return: future value.
        """
        if path not in self._futures:
            self._futures[path] = []
        future: asyncio.Future[SHVType] = asyncio.get_running_loop().create_future()
        self._futures[path].append(future)
        return await future

    async def unsubscribe(self, sub: str, clean_cache: bool = True) -> bool:
        """Perform unsubscribe for signals on given path.

        :param sub: SHV RPC subscription to be removed.
        :param wipe_cache: If no longer subscribed paths should be removed from cache or
            not. The default is to remove them but you can also do multiple unsibscribes
            and then call :meth:`clean_cache` for all of the at once.
        :return: ``True`` in case such subscribe was located and ``False`` otherwise.
        """
        res = await super().unsubscribe(sub)
        if res and clean_cache:
            self.clean_cache()
        return res

    def is_subscribed(
        self, path: str, signal: str = "chng", source: str = "get"
    ) -> bool:
        """Check if we are subscribed for given SHV path.

        Subscribed paths are cached and thus this also checks if this path would be
        cached.

        This is only local check. This won't reach the server to verify that all
        subscriptions are still valid (not removed on the server).

        :param path: SHV path
        :param signal: Signal name
        :param source: Method name signal is associated with.
        :return: ``True`` if subscribed for that path and ``False`` otherwise.
        """
        return any(rpcri_match(sub, path, source, signal) for sub in self._subscribes)

    def clean_cache(self) -> None:
        """Remove no longer subscribed paths from cache.

        There is commonly no need to call this method unless you call
        :meth:`unsubscribe` with ``wipe_cache=False``.
        """
        self._cache = {k: v for k, v in self._cache.items() if self.is_subscribed(k)}

    async def log_snapshot(self, path: str) -> None:
        """Get snapshot of the logs.

        Use this to receive old values.

        :param path: SHV path.
        """
        param: SHVMapType = {
            "recordCountLimit": 10000,
            "withPathsDict": True,
            "withSnapshot": True,
            "withTypeInfo": False,
            "since": datetime.datetime.now(),
        }
        result = await self.call(path, "getLog", param)
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

    async def get_snapshot(self, *paths: str, update: bool = False) -> None:
        """Get snapshot of data on subscribed paths using get methods.

        This provides a way for you to initialize cache without logs. It
        iterates over SHV tree and calls any get method it encounters.

        :param paths: Paths to be snapshoted. If none is provide the
          subscriptions are used instead.
        :param update: If already cached values should be updated or just
          skipped.
        """
        pths: list[str] = list(paths) if paths else [""]
        # TODO we can skip paths that are outside of our subscriptions
        while pths:
            pth = pths.pop()
            try:
                pths.extend(
                    f"{pth}{'/' if pth else ''}{name}" for name in await self.ls(pth)
                )
            except (RpcMethodNotFoundError, RpcMethodCallExceptionError):
                pass  # ls might not be present which is not an issue
            if not self.is_subscribed(pth) or (not update and pth in self._cache):
                continue
            if await self.dir_exists(pth, "get"):
                self._cache[pth] = (time.time(), await self.prop_get(pth))
