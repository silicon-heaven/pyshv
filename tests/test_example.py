"""Perform tests of our examples."""
import pytest

import example_client
from shv import RpcMethodNotFoundError, shvmeta_eq


@pytest.mark.parametrize(
    "path,result",
    (
        ("", [".broker", "test"]),
        ("test", ["device"]),
        ("test/device", [".app", "track"]),
        ("test/device/track", [str(i) for i in range(1, 9)]),
    ),
)
async def test_ls(example_device, client, path, result):
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
            ],
        ),
        (
            "test/device/.app",
            [
                {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "dir"},
                {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "ls"},
                {
                    "accessGrant": "bws",
                    "flags": 2,
                    "name": "shvVersionMajor",
                    "signature": 2,
                },
                {
                    "accessGrant": "bws",
                    "flags": 2,
                    "name": "shvVersionMinor",
                    "signature": 2,
                },
                {"accessGrant": "bws", "flags": 2, "name": "appName", "signature": 2},
                {
                    "accessGrant": "bws",
                    "flags": 2,
                    "name": "appVersion",
                    "signature": 2,
                },
                {"accessGrant": "bws", "flags": 0, "name": "ping", "signature": 0},
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
async def test_dir(example_device, client, path, result):
    res = await client.call(path, "dir")
    print(res)
    assert shvmeta_eq(res, result)


async def test_get(example_device, client):
    res = await client.call("test/device/track/4", "get")
    assert res == [0, 1, 2, 3]


async def test_set(example_device, client):
    tracks = [3, 2, 1, 0]
    res = await client.call("test/device/track/4", "set", tracks)
    assert res is True

    res = await client.call("test/device/track/4", "get")
    assert shvmeta_eq(res, tracks)


async def test_invalid_request(example_device, client):
    with pytest.raises(RpcMethodNotFoundError):
        await client.call("test/device/track/4", "nosuchmethod")


async def test_no_such_node(example_device, client):
    with pytest.raises(RpcMethodNotFoundError):
        await client.ls("test/device/track/none")
    with pytest.raises(RpcMethodNotFoundError):
        await client.dir("test/device/track/none")


async def test_example_client(shvbroker, url):
    await example_client.example_client(url)
