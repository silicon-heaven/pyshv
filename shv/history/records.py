"""The database used to store history."""

from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import enum
import sqlite3
import typing

from .. import (
    ChainPack,
    DefaultRpcSubscription,
    RpcMethodAccess,
    RpcSubscription,
    SHVType,
)
from .log import RpcLog
from .record import RpcHistoryRecord


@dataclasses.dataclass
class RpcHistoryRecordDB(RpcHistoryRecord):
    """Record keeped by RPC History exnteded by database ID."""

    dbid: int = 0
    """ID of the record in the database."""

    class SHVKey(enum.IntEnum):
        """Keys used to pack fields to IMap."""

        ID = enum.auto()
        TIME_MONOTONIC = enum.auto()
        TIME_DEVICE = enum.auto()
        PATH = enum.auto()
        SIGNAL = enum.auto()
        SOURCE = enum.auto()
        DATA = enum.auto()
        USER_ID = enum.auto()
        ACCESS_LEVEL = enum.auto()
        SNAPSHOT = enum.auto()

    def to_shv(self) -> SHVType:
        """Convert to SHV."""
        res: dict[int, SHVType] = {
            self.SHVKey.ID: int(self.dbid),
            self.SHVKey.TIME_MONOTONIC: self.time_monotonic,
            self.SHVKey.PATH: self.path,
            self.SHVKey.SIGNAL: self.signal,
            self.SHVKey.SOURCE: self.source,
            self.SHVKey.DATA: self.data,
            self.SHVKey.ACCESS_LEVEL: self.access,
            self.SHVKey.SNAPSHOT: self.snapshot,
        }
        if self.time_device is not None:
            res[self.SHVKey.TIME_DEVICE] = self.time_device
        if self.user_id is not None:
            res[self.SHVKey.USER_ID] = self.user_id
        return res


class RpcLogRecords(RpcLog):
    """Databse records wrapper for SHV RPC history."""

    def __init__(
        self,
        sqldb: sqlite3.Connection,
        name: str,
        subscriptions: collections.abc.Set[RpcSubscription] = frozenset(),
    ) -> None:
        super().__init__(name, subscriptions)
        self._db = sqldb
        with self._db as con:
            con.execute(
                f"CREATE TABLE IF NOT EXISTS shv1_records_{name}("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + "timemono TEXT NOT NULL,"
                + "timedev TEXT,"
                + "path TEXT NOT NULL,"
                + "signal TEXT NOT NULL,"
                + "source TEXT NOT NULL,"
                + "userid TEXT,"
                + "access INT NOT NULL,"
                + "data BLOB,"
                + "snapshot BOOL"
                + ")"
            )
            con.execute(
                f"CREATE TABLE IF NOT EXISTS shv1_index_{name}("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + "path TEXT NOT NULL,"
                + "signal TEXT NOT NULL,"
                + "source TEXT NOT NULL,"
                + "recordid INT NOT NULL,"
                + "UNIQUE(path, signal, source),"
                + f"FOREIGN KEY (recordid) REFERENCES shv1_records_{name} (id)"
                + ")"
            )

    def _add(self, record: RpcHistoryRecord) -> None:
        """Add given signal record to the database."""
        with self._db as con:
            cur = con.cursor()
            last_time = cur.execute(
                "SELECT timemono FROM ? WHERE id IN ( SELECT max(id) FROM ? );",
                (f"shv1_records_{self._name}", f"shv1_records_{self._name}"),
            ).fetchone()
            if last_time is not None:
                last_datetime = datetime.datetime.fromisoformat(last_time[0])
                if last_datetime > record.time_monotonic:
                    record = dataclasses.replace(
                        record,
                        time_device=record.time_monotonic,
                        time_monotonic=last_datetime,
                    )
            cur.execute(
                "INSERT INTO ? VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"shv1_records_{self._name}",
                    record.time_monotonic,
                    record.time_device,
                    record.path,
                    record.signal,
                    record.source,
                    record.user_id,
                    record.access,
                    ChainPack.pack(record.data),
                    record.snapshot,
                ),
            )
            lastid = cur.lastrowid
            assert lastid is not None
            cur.execute(
                "INSERT OR REPLACE INTO :table VALUES ((SELECT id FROM :table WHERE path=:path AND signal=:signal AND source=:source), :path, :signal, :source, :rowid)",
                {
                    "table": f"shv1_index_{self._name}",
                    "path": record.path,
                    "signal": record.signal,
                    "source": record.source,
                    "rowid": lastid,
                },
            )

            span_edge = 2 * self._unique_records() - 1
            while rec := cur.execute(
                "SELECT id FROM ? WHERE recordid=?",
                (f"shv1_index_{self._name}", lastid - span_edge),
            ).fetchone():
                cur.execute(
                    f"INSERT INTO shv1_records_{self._name} "
                    + "SELECT NULL, ?, ?, path, signal, source, userid, access, data, TRUE "
                    + f"FROM shv1_records_{self._name} WHERE id=?",
                    (record.time_monotonic, record.time_device, lastid - span_edge),
                )
                assert lastid + 1 == cur.lastrowid
                lastid = cur.lastrowid
                cur.execute(
                    "UPDATE ? SET recordid=? WHERE id=?",
                    (f"shv1_index_{self._name}", lastid, rec[0]),
                )

    def _unique_records(self) -> int:
        rec = self._db.execute(
            "SELECT COUNT(*) FROM ?", (f"shv1_index_{self._name}",)
        ).fetchone()
        return int(rec[0]) if rec is not None else 0

    def nodes(self, path: str) -> collections.abc.Iterator[str]:  # noqa: D102
        return (
            pth[0][len(path) + (1 if path else 0) :].partition("/")[0]
            for pth in self._db.execute(
                "SELECT DISTINCT path FROM ? WHERE path LIKE ?",
                (
                    f"shv1_index_{self._name}",
                    path.replace("%", "\\%").replace("_", "\\_") + "/%"
                    if path
                    else "%",
                ),
            )
        )

    def snapshot(  # noqa: D102
        self, date: datetime.datetime, sub: RpcSubscription = DefaultRpcSubscription
    ) -> collections.abc.Iterator[RpcHistoryRecordDB]:
        yielded = set()
        for r in self._db.execute(
            "SELECT * FROM  WHERE :table id <= (SELECT id FROM :table WHERE timemono <= :date ORDER BY timemono DESC LIMIT 1) ORDER BY id DESC LIMIT count",
            {
                "table": f"shv1_records_{self._name}",
                "date": date,
                "count": 2 * self._unique_records(),
            },
        ):
            rid = (r[3], r[4], r[5])
            if rid in yielded:
                continue
            yielded.add(rid)
            if sub.applies(r[3], r[4], r[5]):
                yield self._record(r)

    def get(  # noqa: D102
        self, since: datetime.datetime, until: datetime.datetime, sub: RpcSubscription
    ) -> collections.abc.Iterator[RpcHistoryRecordDB]:
        for r in self._db.execute(
            "SELECT * FROM ? WHERE timemono >= ? AND timemono <= ?",
            (f"shv1_records_{self._name}", since, until),
        ):
            if not sub.applies(r[3], r[4], r[5]):
                continue
            yield self._record(r)

    def span(self) -> tuple[int, int, int]:
        """Span of the logs in the database.

        This returns tuple with:
        * Lowest ID in the database
        * Highest ID in the database
        * The snapshot span (that is span in which all records are repeated)
        """
        limits = self._db.execute(
            "SELECT MIN(id), MAX(id) FROM ?", (f"shv1_records_{self._name}",)
        ).fetchone()
        return (limits[0] or 0, limits[1] or 0, self._unique_records() * 2)

    def records(
        self, offset: int, count: int
    ) -> collections.abc.Iterator[RpcHistoryRecordDB]:
        """Iterate over records from start to end index.

        :param offset: The ID of the first record to be provided.
        :param count: Maximum number of records to provide.
        """
        for r in self._db.execute(
            "SELECT * FROM ? WHERE id >= ? AND id < ?",
            (f"shv1_records_{self._name}", offset, offset + count),
        ):
            yield self._record(r)

    @staticmethod
    def _record(record: typing.Any) -> RpcHistoryRecordDB:  # noqa ANN401
        return RpcHistoryRecordDB(
            record[3],
            record[4],
            record[5],
            ChainPack.unpack(record[8]),
            record[6],
            RpcMethodAccess(int(record[7])),
            bool(record[9]),
            datetime.datetime.fromisoformat(record[1]),
            datetime.datetime.fromisoformat(record[2])
            if record[2] is not None
            else None,
            record[0],
        )
