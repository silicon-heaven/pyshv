"""erform tests of our examples."""

import pytest

import example_client
from shv import RpcMethodAccess, RpcMethodNotFoundError, shvmeta


@pytest.mark.parametrize(
    "path,method,param,result",
    (
        ("", "ls", "test", True),
        ("test", "ls", None, ["device"]),
        ("test/device", "ls", None, [".app", "track"]),
        ("test/device/track", "ls", None, [str(i) for i in range(1, 9)]),
        ("test/device/track", "ls", "1", True),
        ("test/device/track", "ls", "8", True),
        ("test/device/track", "ls", "0", False),
        ("test/device/track", "ls", "9", False),
        (
            "test/device",
            "dir",
            None,
            [
                {1: "dir", 2: 0, 3: "idir", 4: "odir", 5: RpcMethodAccess.BROWSE},
                {
                    1: "ls",
                    2: 0,
                    3: "ils",
                    4: "ols",
                    5: RpcMethodAccess.BROWSE,
                    6: {"lsmod": "olsmod"},
                },
            ],
        ),
        (
            "test/device/.app",
            "dir",
            None,
            [
                {1: "dir", 2: 0, 3: "idir", 4: "odir", 5: RpcMethodAccess.BROWSE},
                {
                    1: "ls",
                    2: 0,
                    3: "ils",
                    4: "ols",
                    5: RpcMethodAccess.BROWSE,
                    6: {"lsmod": "olsmod"},
                },
                {1: "shvVersionMajor", 2: 2, 4: "Int", 5: RpcMethodAccess.READ},
                {1: "shvVersionMinor", 2: 2, 4: "Int", 5: RpcMethodAccess.READ},
                {1: "name", 2: 2, 4: "String", 5: RpcMethodAccess.READ},
                {1: "version", 2: 2, 4: "String", 5: RpcMethodAccess.READ},
                {1: "date", 2: 2, 4: "DateTime", 5: RpcMethodAccess.READ},
                {1: "ping", 2: 0, 5: RpcMethodAccess.BROWSE},
            ],
        ),
        (
            "test/device/track",
            "dir",
            None,
            [
                {1: "dir", 2: 0, 3: "idir", 4: "odir", 5: RpcMethodAccess.BROWSE},
                {
                    1: "ls",
                    2: 0,
                    3: "ils",
                    4: "ols",
                    5: RpcMethodAccess.BROWSE,
                    6: {"lsmod": "olsmod"},
                },
                {
                    1: "reset",
                    2: 32,
                    5: RpcMethodAccess.COMMAND,
                    63: {"dependencies": "Reset all tracks to their initial state"},
                },
                {
                    1: "lastResetUser",
                    2: 2,
                    3: "Int",
                    4: "StringOrNull",
                    5: RpcMethodAccess.READ,
                },
            ],
        ),
        (
            "test/device/track/1",
            "dir",
            None,
            [
                {1: "dir", 2: 0, 3: "idir", 4: "odir", 5: RpcMethodAccess.BROWSE},
                {
                    1: "ls",
                    2: 0,
                    3: "ils",
                    4: "ols",
                    5: RpcMethodAccess.BROWSE,
                    6: {"lsmod": "olsmod"},
                },
                {
                    1: "get",
                    2: 2,
                    3: "Int",
                    4: "List[Int]",
                    5: RpcMethodAccess.READ,
                    6: {"chng": None},
                    63: {"description": "List of tracks"},
                },
                {
                    1: "set",
                    2: 4,
                    3: "List[Int]",
                    5: RpcMethodAccess.WRITE,
                    63: {"description": "Set track"},
                },
            ],
        ),
        ("test/device/track/4", "dir", "get", True),
        ("test/device/track/4", "dir", "set", True),
        ("test/device/track/4", "dir", "chng", False),
        ("test/device/track/4", "get", None, [0, 1, 2, 3]),
    ),
)
async def test_call(example_device, client, path, method, param, result):
    res = await client.call(path, method, param)
    assert res == result
    assert shvmeta(res) == shvmeta(result)


async def test_set(example_device, client):
    tracks = [3, 2, 1, 0]
    assert await client.call("test/device/track/4", "set", tracks) is None

    res = await client.call("test/device/track/4", "get")
    assert res == tracks
    assert shvmeta(res) == shvmeta(tracks)


async def test_reset(example_device, value_client):
    await value_client.prop_set("test/device/track/2", [42] * 8)
    await value_client.subscribe("test/device/**:*:*")
    assert await value_client.call("test/device/track", "reset") is None
    # Reset should send update on track 2 because it was changed
    assert value_client["test/device/track/2"] == [0, 1]
    # No other notification should be received
    assert len(value_client) == 1
    assert (
        await value_client.call("test/device/track", "lastResetUser")
        == "test:testbroker"
    )


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
