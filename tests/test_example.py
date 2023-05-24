"""Perform tests of our examples."""
import asyncio
import dataclasses

import pytest

import example_client
from example_device import example_device
from shv import RpcMethodNotFoundError, RpcUrl, shvmeta_eq


@pytest.fixture(name="device")
async def fixture_device(event_loop, shvbroker, url):
    """Run example device and provide socket to access it."""
    nurl = dataclasses.replace(url, device_mount_point="test/device")
    task = event_loop.create_task(example_device(nurl))
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
                {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "dir"},
                {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "ls"},
                {"accessGrant": "rd", "flags": 2, "name": "appName", "signature": 2},
                {"accessGrant": "rd", "flags": 2, "name": "appVersion", "signature": 2},
                {"accessGrant": "wr", "flags": 0, "name": "echo", "signature": 3},
            ],
        ),
        (
            "test/device/track",
            [
                {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "dir"},
                {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "ls"},
            ],
        ),
        (
            "test/device/track/1",
            [
                {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "dir"},
                {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "ls"},
                {
                    "accessGrant": "rd",
                    "flags": 2,
                    "signature": 2,
                    "name": "get",
                    "description": "Get current track",
                },
                {
                    "accessGrant": "wr",
                    "flags": 4,
                    "signature": 1,
                    "name": "set",
                    "description": "Set track",
                },
            ],
        ),
    ),
)
async def test_dir(device, client, path, result):
    res = await client.call(path, "dir", ("", 127))
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


async def test_example_client(shvbroker, url):
    await example_client.example_client(url)
