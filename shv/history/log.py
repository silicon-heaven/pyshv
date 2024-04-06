"""The implementation of the log that can access database as well as files."""

import abc
import collections.abc
import datetime

from .. import RpcSubscription
from .record import RpcHistoryRecord


class RpcLog(abc.ABC):
    """Generic history log."""

    def __init__(
        self,
        name: str,
        subscriptions: collections.abc.Set[RpcSubscription] = frozenset(),
    ) -> None:
        if "/" in name:
            raise ValueError("Log name can't contain '/'")
        self._name = name
        self._subscriptions = subscriptions

    @property
    def name(self) -> str:
        """Name of this log."""
        return self._name

    def subscriptions(self) -> collections.abc.Iterator[RpcSubscription]:
        """Iterate over subscriptions this log requires."""
        yield from self._subscriptions

    def add(self, record: RpcHistoryRecord) -> None:
        """Add new record to the log."""
        if any(
            s.applies(record.path, record.signal, record.source)
            for s in self._subscriptions
        ):
            self._add(record)

    @abc.abstractmethod
    def _add(self, record: RpcHistoryRecord) -> None: ...

    @abc.abstractmethod
    def nodes(self, path: str) -> collections.abc.Iterator[str]:
        """Iterate over nodes that this log recorded signals from.

        This is needed to get visualization of the node tree.

        :param path: SHV path iterated list should be direct children of.
        :return: Iterator over path's children nodes.
        """

    @abc.abstractmethod
    def snapshot(
        self, date: datetime.datetime, sub: RpcSubscription
    ) -> collections.abc.Iterator[RpcHistoryRecord]:
        """Query log to receive snapshot of all recorded signals at given time.

        :param self:
        :param date:
        :param sub:
        :return:
        """

    @abc.abstractmethod
    def get(
        self, since: datetime.datetime, until: datetime.datetime, sub: RpcSubscription
    ) -> collections.abc.Iterator[RpcHistoryRecord]:
        """Query log.

        :param self:
        :param since:
        :param until:
        :param sub:
        :return:
        """


class RpcLogClone(RpcLog):
    """History log that is clone of logs from other history."""

    def __init__(self, name: str, shvpath: str) -> None:
        super().__init__(name)
        if not shvpath:
            raise ValueError("SHV path can't be root")
        self._shvpath = shvpath

    @property
    def shvpath(self) -> str:
        """SHV path of this pulled log."""
        return self._shvpath
