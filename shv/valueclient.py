"""Common extension for the SimpleClient."""
import collections.abc
import datetime
import typing

from .rpcclient import RpcClient
from .simpleclient import SimpleClient
from .value import SHVType, shvmeta, shvmeta_eq


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
