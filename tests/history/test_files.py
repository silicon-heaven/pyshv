"""Check that our files abstraction works."""

import datetime

import pytest

from shv import Cpon, RpcMethodAccess, RpcSubscription
from shv.history import RpcHistoryRecord, RpcLogFiles


@pytest.fixture(name="files")
def fixture_files(files_path):
    return RpcLogFiles(files_path, "all", [RpcSubscription()])


@pytest.fixture(name="records")
def fixture_records():
    now = datetime.datetime.now().astimezone()
    return [
        RpcHistoryRecord(
            "test/device",
            "chng",
            "get",
            23,
            None,
            RpcMethodAccess.READ,
            False,
            now,
            None,
        ),
        RpcHistoryRecord(
            "test/device",
            "chng",
            "get",
            25,
            None,
            RpcMethodAccess.READ,
            False,
            now + datetime.timedelta(seconds=1),
            None,
        ),
        RpcHistoryRecord(
            "test/device/status",
            "chng",
            "get",
            False,
            None,
            RpcMethodAccess.READ,
            False,
            now + datetime.timedelta(seconds=2),
            None,
        ),
    ]


@pytest.fixture(name="seeded")
def fixture_seeded(files, records):
    files.add(records[0])
    files.add(records[1])
    files.add(records[2])
    return files


@pytest.fixture(name="fragmented")
def fixture_fragmented(files_path, records):
    RpcLogFiles(files_path, "all", [RpcSubscription()]).add(records[0])
    RpcLogFiles(files_path, "all", [RpcSubscription()]).add(records[1])
    RpcLogFiles(files_path, "all", [RpcSubscription()]).add(records[2])
    return RpcLogFiles(files_path, "all", [RpcSubscription()])


def test_files(seeded, records):
    assert list(seeded.files()) == [
        f"{records[0].time_monotonic.replace(microsecond=0).isoformat()}.log3"
    ]


def test_files_fragmented(fragmented, records):
    assert list(fragmented.files()) == [
        f"{records[0].time_monotonic.replace(microsecond=0).isoformat()}.log3",
        f"{records[1].time_monotonic.replace(microsecond=0).isoformat()}.log3",
        f"{records[2].time_monotonic.replace(microsecond=0).isoformat()}.log3",
    ]


def test_content(seeded, files_path, records):
    lines = [
        f'[{Cpon.pack(records[0].time_monotonic)},null,"test/device","chng","get",null,8,23,false]',
        f'[{Cpon.pack(records[1].time_monotonic)},null,"test/device","chng","get",null,8,25,false]',
        f'[{Cpon.pack(records[2].time_monotonic)},null,"test/device/status","chng","get",null,8,false,false]',
    ]
    file = (
        files_path
        / f"{records[0].time_monotonic.replace(microsecond=0).isoformat()}.log3"
    )
    with file.open("r") as f:
        assert f.read() == "\n".join(lines) + "\n"


def test_content_fragmented(seeded, files_path, records):
    lines = [
        f'[{Cpon.pack(records[0].time_monotonic)},null,"test/device","chng","get",null,8,23,false]',
        f'[{Cpon.pack(records[1].time_monotonic)},null,"test/device","chng","get",null,8,25,false]',
        f'[{Cpon.pack(records[2].time_monotonic)},null,"test/device/status","chng","get",null,8,false,false]',
    ]
    file = (
        files_path
        / f"{records[0].time_monotonic.replace(microsecond=0).isoformat()}.log3"
    )
    with file.open("r") as f:
        assert f.read() == "\n".join(lines) + "\n"
