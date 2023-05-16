"""Perform tests of our examples."""
import asyncio

import pytest

import example_client
import shv
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
    await client.call_shv_method(path, "ls")
    resp = await client.read_rpc_message()
    assert resp.result() == result


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
    await client.call_shv_method(path, "dir")
    resp = await client.read_rpc_message()
    assert resp.result() == result


async def test_get(device, client):
    await client.call_shv_method("test/device/track/4", "get")
    resp = await client.read_rpc_message()
    assert resp.result() == [0, 1, 2, 3]


async def test_set(device, client):
    tracks = [3, 2, 1, 0]
    await client.call_shv_method("test/device/track/4", "set", tracks)
    resp = await client.read_rpc_message()
    assert resp.result() is True

    await client.call_shv_method("test/device/track/4", "get")
    resp = await client.read_rpc_message()
    assert resp.result() == tracks


async def test_invalid_request(device, client):
    await client.call_shv_method("test/device/track/4", "nosuchmethod")
    with pytest.raises(shv.RpcError):
        await client.read_rpc_message()


async def test_example_client(shvbroker, port):
    await example_client.test(port=port)
