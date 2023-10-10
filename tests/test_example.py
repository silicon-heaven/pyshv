"""Perform tests of our examples."""
import pytest

import example_client
from shv import RpcMethodNotFoundError, shvmeta_eq


@pytest.mark.parametrize(
    "path,result",
    (
        ("", [".broker", "test"]),
        ("test", ["device", "someInt", "someText", "uptime"]),
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
                {1: "dir", 2: 0, 3: "idir", 4: "odir", 5: "bws"},
                {1: "ls", 2: 0, 3: "ils", 4: "ols", 5: "bws"},
                {1: "lschng", 2: 1, 4: "olschng", 5: "bws"},
            ],
        ),
        (
            "test/device/.app",
            [
                {1: "dir", 2: 0, 3: "idir", 4: "odir", 5: "bws"},
                {1: "ls", 2: 0, 3: "ils", 4: "ols", 5: "bws"},
                {1: "lschng", 2: 1, 4: "olschng", 5: "bws"},
                {1: "shvVersionMajor", 2: 2, 4: "Int", 5: "rd"},
                {1: "shvVersionMinor", 2: 2, 4: "Int", 5: "rd"},
                {1: "name", 2: 2, 4: "String", 5: "rd"},
                {1: "version", 2: 2, 4: "String", 5: "rd"},
                {1: "ping", 2: 0, 5: "bws"},
            ],
        ),
        (
            "test/device/track",
            [
                {1: "dir", 2: 0, 3: "idir", 4: "odir", 5: "bws"},
                {1: "ls", 2: 0, 3: "ils", 4: "ols", 5: "bws"},
                {1: "lschng", 2: 1, 4: "olschng", 5: "bws"},
            ],
        ),
        (
            "test/device/track/1",
            [
                {1: "dir", 2: 0, 3: "idir", 4: "odir", 5: "bws"},
                {1: "ls", 2: 0, 3: "ils", 4: "ols", 5: "bws"},
                {1: "lschng", 2: 1, 4: "olschng", 5: "bws"},
                {1: "get", 2: 2, 3: "Int", 4: "List[Int]", 5: "rd"},
                {1: "set", 2: 4, 3: "List[Int]", 5: "wr"},
            ],
        ),
    ),
)
async def test_dir(example_device, client, path, result):
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
