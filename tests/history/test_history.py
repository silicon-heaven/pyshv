"""Check that history works correctly."""

import collections.abc
import datetime
import logging

import pytest

from shv import (
    RpcMethodAccess,
    RpcMethodDesc,
    RpcMethodFlags,
    RpcSubscription,
    SimpleDevice,
)
from shv.history import RpcHistoryClient, RpcLogRecords

logger = logging.getLogger(__name__)


class OurDevice(SimpleDevice):
    """Device we use to send notifications we want to store to history."""

    async def signal(self, *args, **kwargs) -> None:
        await self._signal(*args, **kwargs)


@pytest.fixture(name="device")
async def fixture_device(shvbroker, url_test_device):
    device = await OurDevice.connect(url_test_device)
    yield device
    await device.disconnect()


@pytest.fixture(name="records")
def fixture_records(db):
    return RpcLogRecords(db, "all", {RpcSubscription()})


@pytest.fixture(name="history")
async def fixture_history(shvbroker, url, records):
    client = await RpcHistoryClient.connect(url, {records})
    yield client
    await client.disconnect()


@pytest.fixture(name="history_chng")
async def fixture_history_chng(history, device):
    await history.subscribe(RpcSubscription(signal="*chng"))
    await device.signal("", "lsmod", "ls", {"foo": True})
    await device.signal("foo", "chng", "get", 42)
    await device.signal("", "lsmod", "ls", {"foo": False})
    return history


@pytest.mark.parametrize(
    "path,expected",
    (
        ("", [".app", ".history", "test"]),
        ("test/device", [".app"]),
        (".history", [".app", ".records"]),
        (".history/.records", ["all"]),
        (".history/.records/all", []),
    ),
)
async def test_ls(client, history_chng, device, path, expected):
    assert await client.ls(path) == expected


@pytest.mark.skip
@pytest.mark.parametrize(
    "path,expected",
    (
        (
            ".history",
            [RpcMethodDesc.stddir(), RpcMethodDesc.stdls()],
        ),
        (
            ".history/.records",
            [RpcMethodDesc.stddir(), RpcMethodDesc.stdls()],
        ),
        (
            ".history/.records/all",
            [
                RpcMethodDesc.stddir(),
                RpcMethodDesc.stdls(),
                RpcMethodDesc(
                    "span",
                    RpcMethodFlags.GETTER,
                    "Null",
                    "oSpan",
                    RpcMethodAccess.SUPER_SERVICE,
                ),
                RpcMethodDesc(
                    "fetch",
                    RpcMethodFlags(0),
                    "iFetch",
                    "oFetch",
                    RpcMethodAccess.SUPER_SERVICE,
                ),
            ],
        ),
    ),
)
async def test_dir(client, history_chng, path, expected):
    assert await client.dir(path) == expected


@pytest.mark.skip
@pytest.mark.parametrize(
    "path,method,param,expected",
    (
        (".history/.records/all", "span", None, [1, 3, 4]),
        (".history/.records/all", "fetch", [1, 0], []),
    ),
)
async def test_call(client, history_chng, path, method, param, expected):
    assert await client.call(path, method, param) == expected


@pytest.mark.parametrize(
    "path,param,expected",
    (
        (
            ".history/.records/all",
            [1, 2],
            [
                {
                    1: 1,
                    2: datetime.datetime.fromtimestamp(42),
                    4: "test/device",
                    5: "lschng",
                    6: {"foo": True},
                    8: 2,
                    9: 0,
                },
                {
                    1: 2,
                    2: datetime.datetime.fromtimestamp(43),
                    4: "test/device/foo",
                    5: "chng",
                    6: 42,
                    8: 2,
                    9: 0,
                },
            ],
        ),
        (
            ".history/.records/all",
            [2, 2],
            [
                {
                    1: 2,
                    2: datetime.datetime.fromtimestamp(42),
                    4: "test/device/foo",
                    5: "chng",
                    6: 42,
                    8: 2,
                    9: 0,
                },
                {
                    1: 3,
                    2: datetime.datetime.fromtimestamp(43),
                    4: "test/device",
                    5: "lschng",
                    6: {"foo": False},
                    8: 2,
                    9: 0,
                },
            ],
        ),
        (
            ".history/.records/all",
            [1, 5],
            [
                {
                    1: 1,
                    2: datetime.datetime.fromtimestamp(42),
                    4: "test/device",
                    5: "lschng",
                    6: {"foo": True},
                    8: 2,
                    9: 0,
                },
                {
                    1: 2,
                    2: datetime.datetime.fromtimestamp(43),
                    4: "test/device/foo",
                    5: "chng",
                    6: 42,
                    8: 2,
                    9: 0,
                },
                {
                    1: 3,
                    2: datetime.datetime.fromtimestamp(44),
                    4: "test/device",
                    5: "lschng",
                    6: {"foo": False},
                    8: 2,
                    9: 0,
                },
            ],
        ),
    ),
)
async def test_records_fetch(client, history_chng, path, param, expected):
    res = await client.call(path, "fetch", param)
    assert isinstance(res, collections.abc.Sequence)
    for i, v in enumerate(res):
        assert isinstance(v, collections.abc.Mapping)
        assert isinstance(v[2], datetime.datetime)
        v[2] = datetime.datetime.fromtimestamp(42 + i)
    assert res == expected
