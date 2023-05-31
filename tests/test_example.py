"""Perform tests of our examples."""
import pytest

import example_client
from shv import RpcMethodNotFoundError, shvmeta_eq

LS_DATA: list[tuple[str, list[tuple[str, bool | None]]]] = [
    ("", [(".broker", True), ("test", True)]),
    ("test", [("device", None)]),
    ("test/device", [("track", True)]),
    ("test/device/track", [(str(i), False) for i in range(1, 9)]),
]


@pytest.mark.parametrize(
    "path,result", [(c[0], list(v[0] for v in c[1])) for c in LS_DATA]
)
async def test_ls(example_device, client, path, result):
    res = await client.call(path, "ls")
    assert shvmeta_eq(res, result)


@pytest.mark.parametrize("path,result", LS_DATA)
async def test_ls_with_children(example_device, client, path, result):
    res = await client.call(path, "ls", ("", 1))
    assert shvmeta_eq(res, result)


DIR_DATA = [
    (
        "test/device",
        [
            {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "dir"},
            {"accessGrant": "bws", "flags": 0, "signature": 3, "name": "ls"},
            {"accessGrant": "bws", "flags": 2, "name": "appName", "signature": 2},
            {
                "accessGrant": "bws",
                "flags": 2,
                "name": "appVersion",
                "signature": 2,
            },
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
]


@pytest.mark.parametrize(
    "path,result", [(c[0], list(v["name"] for v in c[1])) for c in DIR_DATA]
)
async def test_dir(example_device, client, path, result):
    res = await client.call(path, "dir", ("", 0))
    assert shvmeta_eq(res, result)


@pytest.mark.parametrize("path,result", DIR_DATA)
async def test_dir_details(example_device, client, path, result):
    res = await client.call(path, "dir")
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
