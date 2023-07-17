"""Common extension for the SimpleClient."""
import asyncio
import collections.abc
import datetime
import time
import typing

from .rpcclient import RpcClient
from .simpleclient import SimpleClient
from .value import SHVType, shvmeta, shvmeta_eq


class ValueClient(SimpleClient, collections.abc.Mapping):
    """SHV client made to track values more easily.

    This tailors to the use case of tracking and accessing various values more
    easily. You need to subscribe to specific path and this class automatically
    provides you with cached latest value as received through signals or fetched
    from logs (logs fetching has to be performed explicitly) or with prop_get.

    To access subscribed value you can index this object with SHV path to it.
    """

    def __init__(self, client: RpcClient, client_id: int | None):
        super().__init__(client, client_id)
        self._subscribes: set[str] = set()
        self._cache: dict[str, SHVType] = {}
        self._handlers: dict[
            str, typing.Callable[[ValueClient, str, SHVType], None]
        ] = {}
        self._futures: dict[str, list[asyncio.Future]] = {}

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
        for future in self._futures.pop(path, []):
            future.set_result(value)
        if self.is_subscribed(path):
            self._cache[path] = value

    def _get_handler(
        self, path: str
    ) -> None | typing.Callable[["ValueClient", str, SHVType], None]:
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
        """Get value from the property associated with the node on given path.

        This always calls get method compared to item access that is served only from
        cache.

        :param path: SHV path to the property node.
        :return: Value of the property node.
        """
        value = await self.call(path, "get")
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
        timeout: float = 5.0,
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
        :param timeout: How long we should wait for change. Pass negative number to wait
            infinitely. This is only minimal deadline. The check for it is performed
            only on multiples of ``get_period``.
        :param get_period: How often the pooling should be performed.
        """
        init = self._cache.get(path, None) if value is None else value
        is_subscibed = self.is_subscribed(path)
        if is_subscibed:
            future = self.future_change(path)
        tstart = time.monotonic()
        while timeout < 0 or time.monotonic() - tstart < timeout:
            if is_subscibed:
                try:
                    await asyncio.wait_for(future, get_period)
                    return future.result()
                except TimeoutError:
                    pass
            else:
                await asyncio.sleep(get_period)
            value = await self.prop_get(path)
            if init != value:
                return value
        raise TimeoutError

    def on_change(
        self,
        path: str,
        callback: typing.Callable[["ValueClient", str, SHVType], None] | None,
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

    def future_change(self, path: str) -> asyncio.Future:
        """Provides a way to await for the future change signal.

        Compared to the :meth:`on_change` the path has to match exactly.

        :param path: SHV path to the node the change signal is expected on.
        :return: future value.
        """
        if path not in self._futures:
            self._futures[path] = []
        future = asyncio.get_running_loop().create_future()
        self._futures[path].append(future)
        return future

    async def subscribe(self, path: str) -> None:
        await super().subscribe(path)
        self._subscribes.add(path)

    async def unsubscribe(self, path: str) -> bool:
        res = await super().unsubscribe(path)
        if res:
            self._subscribes.remove(path)
        return res

    def is_subscribed(self, path: str) -> bool:
        """Check if we are subscribed for given SHV path.

        Subscribed paths are cached and this this is also check if this path would be
        cached.

        :param path: SHV path to
        :return: ``True`` if subscribed for that path and ``False`` otherwise.
        """
        return any(path.startswith for v in self._subscribes)

    async def log_snapshot(self, path: str) -> None:
        """Get snapshot of the logs.

        Use this to receive old values.

        :param path: SHV path.
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
