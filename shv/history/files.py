"""The files used to store history."""

import collections.abc
import dataclasses
import datetime
import itertools
import logging
import pathlib
import typing

from .. import Cpon, DefaultRpcSubscription, RpcMethodAccess, RpcSubscription
from .log import RpcLog
from .record import RpcHistoryRecord

logger = logging.getLogger(__name__)


class RpcLogFiles(RpcLog):
    """Wrapper for SHV RPC history files."""

    def __init__(
        self,
        path: pathlib.Path,
        name: str,
        subscriptions: collections.abc.Set[RpcSubscription] = frozenset(),
        *,
        maxsiz: int = 2**20,
        maxage: datetime.timedelta = datetime.timedelta(days=1),
    ) -> None:
        super().__init__(name, subscriptions)
        self.maxsiz = maxsiz
        """The maximum size of the log in bytes before a new log is established."""
        self.maxage = maxage
        """Maximum time length of the log before a new log is established."""
        self._path = path
        self._file: typing.IO | None = None
        self._recreate_after: datetime.datetime | None = None
        self._last_record: datetime.datetime | None = None
        self._snapshot: dict[tuple[str, str, str], RpcHistoryRecord] = {}
        if fpth := self._select_file(None):
            for record in self._read_file(fpth):
                self._snapshot[(record.path, record.signal, record.source)] = record
                self._last_record = record.time_monotonic

    def _add(self, record: RpcHistoryRecord) -> None:
        if self._last_record is not None and self._last_record > record.time_monotonic:
            record = dataclasses.replace(
                record,
                time_device=record.time_monotonic,
                time_monotonic=self._last_record,
            )
        self._last_record = record.time_monotonic
        if (
            self._file is None
            or self._file.tell() > self.maxsiz
            or (
                self._recreate_after is not None
                and self._recreate_after < record.time_monotonic
            )
        ):
            self._path.mkdir(parents=True, exist_ok=True)
            self._recreate_after = record.time_monotonic + self.maxage
            for i in itertools.count():
                fpath = self._path / (
                    record.time_monotonic.replace(microsecond=0).isoformat()
                    + (f"-{i}" if i else "")
                    + ".log3"
                )
                if not fpath.exists():
                    break
            self._file = fpath.open("x", encoding="utf-8")
            for rec in self._snapshot.values():
                self._file.write(
                    self._rec2str(
                        dataclasses.replace(
                            rec,
                            snapshot=True,
                            time_monotonic=record.time_monotonic,
                            time_device=record.time_device,
                        )
                    )
                    + "\n"
                )
            if self._file.tell() * 2 > self.maxsiz:
                logger.warning("%s: Size fragmentation is set too low!", self._path)
        self._file.write(self._rec2str(record) + "\n")
        self._file.flush()
        self._snapshot[(record.path, record.signal, record.source)] = record

    def nodes(self, path: str) -> collections.abc.Iterator[str]:  # noqa: D102
        raise NotImplementedError

    def snapshot(  # noqa: D102
        self, date: datetime.datetime, sub: RpcSubscription = DefaultRpcSubscription
    ) -> collections.abc.Iterator[RpcHistoryRecord]:
        raise NotImplementedError

    def get(  # noqa: D102
        self, since: datetime.datetime, until: datetime.datetime, sub: RpcSubscription
    ) -> collections.abc.Iterator[RpcHistoryRecord]:
        raise NotImplementedError

    def _select_file(self, dt: datetime.datetime | None) -> pathlib.Path | None:
        """Choose log file that can contain given date and time or latest (``None``).

        It can return ``None`` if date and time preceedes even the oldest file.
        """
        return next(
            (
                pth
                for pth in sorted(self._path.glob("*.log3"), reverse=True)
                if dt is None or datetime.datetime.fromisoformat(pth.name[:-5]) < dt
            ),
            None,
        )

    @classmethod
    def _read_file(
        cls, path: pathlib.Path
    ) -> collections.abc.Iterator[RpcHistoryRecord]:
        """Iterate over records in the file."""
        with path.open("r", encoding="utf-8") as file:
            for i, line in enumerate(file):
                try:
                    yield cls._str2rec(line)
                except ValueError as exc:
                    raise ValueError(f"Invalid record {path}:{i}") from exc

    @staticmethod
    def _rec2str(record: RpcHistoryRecord) -> str:
        return Cpon.pack([
            record.time_monotonic,
            record.time_device,
            record.path,
            record.signal,
            record.source,
            record.user_id,
            int(record.access),
            record.data,
            record.snapshot,
        ])

    @staticmethod
    def _str2rec(line: str) -> RpcHistoryRecord:
        v = Cpon.unpack(line)
        if not (
            isinstance(v, collections.abc.Sequence)
            and isinstance(v[0], datetime.datetime)
            and (isinstance(v[1], datetime.datetime) or v[1] is None)
            and isinstance(v[2], str)
            and isinstance(v[3], str)
            and isinstance(v[4], str)
            and (isinstance(v[5], str) or v[5] is None)
            and isinstance(v[6], int)
            and isinstance(v[8], bool)
        ):
            raise ValueError("Invalid record format")
        return RpcHistoryRecord(
            path=v[2],
            signal=v[3],
            source=v[4],
            data=v[7],
            user_id=v[5],
            access=RpcMethodAccess(v[6]),
            snapshot=v[8],
            time_monotonic=v[0],
            time_device=v[1],
        )

    def files(self) -> collections.abc.Iterator[str]:
        """Itearate over files that are in this log."""
        yield from (str(pth.name) for pth in self._path.glob("*.log3"))

    def path(self, name: str) -> pathlib.Path:
        """Provide path to the file with given name.

        This doesn't validate if such file actually exists.

        :param name: Name of the file to be accessed.
        :return: Path to that file.
        """
        return self._path / name
