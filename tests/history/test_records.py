"""Check that our database abstraction works."""

import dataclasses
import datetime

import pytest

from shv import RpcMethodAccess, RpcSubscription
from shv.history import RpcHistoryRecord, RpcHistoryRecordDB, RpcLogRecords


@pytest.fixture(name="records")
def fixture_records(db):
    return RpcLogRecords(db, "all", [RpcSubscription()])


record1 = RpcHistoryRecord(
    "test/device",
    "chng",
    "get",
    23,
    None,
    RpcMethodAccess.READ,
    False,
    datetime.datetime.now().astimezone(),
    None,
)
record2 = RpcHistoryRecord(
    "test/device",
    "chng",
    "get",
    25,
    None,
    RpcMethodAccess.READ,
    False,
    datetime.datetime.now().astimezone(),
    None,
)
record3 = RpcHistoryRecord(
    "test/device/status",
    "chng",
    "get",
    False,
    None,
    RpcMethodAccess.READ,
    False,
    datetime.datetime.now().astimezone(),
    None,
)


@pytest.fixture(name="seeded")
def fixture_seeded(records):
    records.add(record1)
    records.add(record2)
    records.add(record3)
    return records


def test_span_empty(records):
    assert records.span() == (0, 0, 0)


def test_span(seeded):
    assert seeded.span() == (1, 3, 4)


@pytest.mark.parametrize(
    "path,expected",
    (
        ("", {"test"}),
        ("test", {"device"}),
        ("test/device", {"status"}),
        ("test/device/status", set()),
    ),
)
def test_nodes(seeded, path, expected):
    assert set(seeded.nodes(path)) == expected


def test_span_reopen(seeded, db):
    assert RpcLogRecords(db, "all").span() == (1, 3, 4)


@pytest.mark.parametrize(
    "start,end,expected",
    (
        (
            1,
            3,
            [
                RpcHistoryRecordDB(**dataclasses.asdict(record1), dbid=1),
                RpcHistoryRecordDB(**dataclasses.asdict(record2), dbid=2),
                RpcHistoryRecordDB(**dataclasses.asdict(record3), dbid=3),
            ],
        ),
        (
            1,
            1,
            [
                RpcHistoryRecordDB(**dataclasses.asdict(record1), dbid=1),
            ],
        ),
    ),
)
def test_records(seeded, start, end, expected):
    for rec, ref in zip(seeded.records(start, end), expected, strict=True):
        assert rec == ref


def test_monotonic(seeded):
    """Check if log is kept monotonic even if we log records with old time."""
    oldrec = dataclasses.replace(
        record2,
        data=27,
        time_monotonic=record2.time_monotonic - datetime.timedelta(days=1),
    )
    seeded.add(oldrec)
    assert next(seeded.records(4, 1)) == RpcHistoryRecordDB(
        path=oldrec.path,
        signal=oldrec.signal,
        source=oldrec.source,
        data=oldrec.data,
        user_id=oldrec.user_id,
        access=oldrec.access,
        snapshot=False,
        time_monotonic=record3.time_monotonic,
        time_device=oldrec.time_monotonic,
        dbid=4,
    )


def test_repeat_snapshot(seeded):
    """Check that records are repeated in snapshot."""
    for _ in range(2):
        prevrec = dataclasses.replace(
            record3, time_monotonic=datetime.datetime.now().astimezone()
        )
        seeded.add(prevrec)
    assert seeded.span() == (1, 6, 4)
    assert next(seeded.records(6, 1)) == RpcHistoryRecordDB(
        path=record2.path,
        signal=record2.signal,
        source=record2.source,
        data=record2.data,
        user_id=record2.user_id,
        access=record2.access,
        snapshot=True,
        time_monotonic=prevrec.time_monotonic,
        time_device=prevrec.time_device,
        dbid=6,
    )


@pytest.mark.parametrize(
    "date,sub,expected",
    (
        (
            datetime.datetime.now(),
            RpcSubscription(),
            [
                RpcHistoryRecordDB(**dataclasses.asdict(record3), dbid=3),
                RpcHistoryRecordDB(**dataclasses.asdict(record2), dbid=2),
            ],
        ),
        (
            record2.time_monotonic,
            RpcSubscription(),
            [RpcHistoryRecordDB(**dataclasses.asdict(record2), dbid=2)],
        ),
        (
            record1.time_monotonic,
            RpcSubscription(),
            [RpcHistoryRecordDB(**dataclasses.asdict(record1), dbid=1)],
        ),
        (
            datetime.datetime.now(),
            RpcSubscription(paths="test/device/**"),
            [RpcHistoryRecordDB(**dataclasses.asdict(record3), dbid=3)],
        ),
    ),
)
def test_snapshot(seeded, date, sub, expected):
    assert list(seeded.snapshot(date, sub)) == expected


@pytest.mark.parametrize(
    "since,until,sub,expected",
    (
        (
            record1.time_monotonic,
            datetime.datetime.now(),
            RpcSubscription(),
            [
                RpcHistoryRecordDB(**dataclasses.asdict(record1), dbid=1),
                RpcHistoryRecordDB(**dataclasses.asdict(record2), dbid=2),
                RpcHistoryRecordDB(**dataclasses.asdict(record3), dbid=3),
            ],
        ),
        (
            record1.time_monotonic,
            datetime.datetime.now(),
            RpcSubscription(paths="test/device/**"),
            [RpcHistoryRecordDB(**dataclasses.asdict(record3), dbid=3)],
        ),
    ),
)
def test_get(seeded, since, until, sub, expected):
    assert list(seeded.get(since, until, sub)) == expected
