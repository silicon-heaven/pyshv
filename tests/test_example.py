"""Perform tests of our examples."""
import asyncio

import pytest

import example_client
from shv import shvmeta_eq, RpcMethodNotFoundError
from example_device import example_device


@pytest.fixture(name="device")
async def fixture_device(event_loop, shvbroker, port):
    """Run example device and provide socket to access it."""
    task = event_loop.create_task(example_device(port=port))
    yield task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.parametrize(
    "path,result",
    (
        ("", [".broker", "test"]),
        ("test", ["device"]),
        ("test/device", ["track"]),
        ("test/device/track", [str(i) for i in range(1, 9)]),
    ),
)
async def test_ls(device, client, path, result):
    res = await client.call(path, "ls")
    assert shvmeta_eq(res, result)


@pytest.mark.parametrize(
    "path,result",
    (
        (
            "test/device",
            [
                {"accessGrant": "bws", "flags": 0, "name": "dir"},
                {"accessGrant": "bws", "flags": 0, "name": "ls"},
            ],
        ),
        (
            "test/device/track",
            [
                {"accessGrant": "bws", "flags": 0, "name": "dir"},
                {"accessGrant": "bws", "flags": 0, "name": "ls"},
            ],
        ),
        (
            "test/device/track/1",
            [
                {"accessGrant": "bws", "flags": 0, "name": "dir"},
                {
                    "accessGrant": "rd",
                    "flags": 2,
                    "name": "get",
                },
                {
                    "accessGrant": "wr",
                    "flags": 4,
                    "name": "set",
                },
            ],
        ),
    ),
)
async def test_dir(device, client, path, result):
    res = await client.call(path, "dir")
    assert shvmeta_eq(res, result)


async def test_get(device, client):
    res = await client.call("test/device/track/4", "get")
    assert res == [0, 1, 2, 3]


async def test_set(device, client):
    tracks = [3, 2, 1, 0]
    res = await client.call("test/device/track/4", "set", tracks)
    assert res is True

    res = await client.call("test/device/track/4", "get")
    assert shvmeta_eq(res, tracks)


async def test_invalid_request(device, client):
    with pytest.raises(RpcMethodNotFoundError):
        await client.call("test/device/track/4", "nosuchmethod")


async def test_example_client(shvbroker, port):
    await example_client.test(port=port)
