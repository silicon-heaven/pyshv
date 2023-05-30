"""Check our own implementation of the broker."""
import dataclasses

import pytest

from shv import (
    RpcClient,
    RpcInvalidParamsError,
    RpcInvalidRequestError,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
    SimpleClient,
    ValueClient,
    broker,
    shvmeta_eq,
)


@pytest.fixture(name="shvbroker")
async def fixture_shvbroker(event_loop, config, url):
    config.listen = {"test": url}
    b = broker.RpcBroker(config)
    await b.start_serving()
    event_loop.create_task(b.serve_forever())
    yield broker
    b.close()
    await b.wait_closed()


@pytest.mark.parametrize(
    "path,nodes",
    (
        ("", [".broker"]),
        (".broker", ["app", "clients", "currentClient"]),
        (".broker/app", []),
        (".broker/clients", ["0"]),  # only connection is us
        (".broker/clients/0", ["app"]),
        (".broker/currentClient", []),
    ),
)
async def test_empty_ls(client, path, nodes):
    """Check tree provided by empty broker."""
    assert await client.ls(path) == nodes


@pytest.mark.parametrize(
    "path",
    (
        "foo",
        ".broker/foo",
        ".broker/clients/foo",
    ),
)
async def test_empty_ls_invalid(client, path):
    """Check tree provided by empty broker."""
    with pytest.raises(RpcMethodNotFoundError):
        await client.ls(path)


@pytest.mark.parametrize(
    "path,methods",
    (
        ("", ["dir", "ls", "appName", "appVersion", "echo"]),
        (
            ".broker/app",
            [
                "dir",
                "ls",
                "ping",
                "subscribe",
                "unsubscribe",
                "rejectNotSubscribed",
                "mountPoints",
            ],
        ),
        (".broker/currentClient", ["dir", "ls", "clientId", "mountPoint"]),
        (".broker/clients", ["dir", "ls"]),
        (
            ".broker/clients/0",
            [
                "dir",
                "ls",
                "userName",
                "mountPoint",
                "subscriptions",
                "dropClient",
                "idleTime",
                "idleTimeMax",
            ],
        ),
    ),
)
async def test_empty_dir(client, path, methods):
    """Check tree provided by empty broker."""
    assert await client.dir(path) == methods


@pytest.mark.parametrize(
    "path,method,result",
    (
        (".broker/app", "ping", None),
        (".broker/app", "mountPoints", {}),
        (".broker/currentClient", "clientId", 0),
        (".broker/currentClient", "mountPoint", None),
        (".broker/clients/0", "userName", "admin"),
        (".broker/clients/0", "mountPoint", None),
        (".broker/clients/0", "subscriptions", []),
        (".broker/clients/0", "idleTime", 0),  # we are the one asking
        (".broker/clients/0", "idleTimeMax", 180000),
    ),
)
async def test_empty_call(client, path, method, result):
    """Call various broker methods."""
    assert shvmeta_eq(await client.call(path, method), result)


@pytest.mark.parametrize(
    "path,nodes",
    (
        (".broker/clients", ["0", "1"]),
        ("", [".broker", "test"]),
        ("test/device", ["track"]),
        ("test/device/track", ["1", "2", "3", "4", "5", "6", "7", "8"]),
    ),
)
async def test_with_example_ls(client, example_device, path, nodes):
    assert await client.ls(path) == nodes


async def test_subscribe(client, example_device):
    await client.subscribe("test/device/track")
    assert await client.call(".broker/clients/0", "subscriptions") == [
        {"method": "chng", "path": "test/device/track"}
    ]
    assert await client.unsubscribe("test/device/track") is True
    assert await client.call(".broker/clients/0", "subscriptions") == []
    assert await client.unsubscribe("test/device/track") is False


async def test_reject_not_subscribed(client, example_device):
    await client.subscribe("test/device/track")
    assert (
        await client.call(
            ".broker/app",
            "rejectNotSubscribed",
            {"path": "no/such/node"},
        )
        is False
    )
    assert (
        await client.call(
            ".broker/app",
            "rejectNotSubscribed",
            {"path": "test/device/track/1", "method": "chng"},
        )
        is True
    )


async def test_with_example_set(example_device, url_test):
    """Perform set to trigger also notifications."""
    client = await ValueClient.connect(url_test)
    await client.subscribe("test/device/track")
    await client.prop_set("test/device/track/1", [1, 2])
    assert await client.prop_get("test/device/track/1") == [1, 2]
    assert client["test/device/track/1"] == [1, 2]


async def test_invalid_login(shvbroker, url):
    nurl = dataclasses.replace(url, password="invalid")
    with pytest.raises(RpcMethodCallExceptionError):
        await SimpleClient.connect(nurl)


async def test_invalid_hello_seq(shvbroker, url):
    client = await RpcClient.connect(url.host, url.port, url.protocol)
    await client.call_shv_method(None, "invalid")
    with pytest.raises(RpcInvalidRequestError):
        await client.read_rpc_message()


async def test_invalid_login_seq(shvbroker, url):
    client = await RpcClient.connect(url.host, url.port, url.protocol)
    await client.call_shv_method(None, "hello")
    await client.read_rpc_message()
    await client.call_shv_method(None, "invalid")
    with pytest.raises(RpcInvalidRequestError):
        await client.read_rpc_message()


async def test_invalid_login_null(shvbroker, url):
    client = await RpcClient.connect(url.host, url.port, url.protocol)
    await client.call_shv_method(None, "hello")
    await client.read_rpc_message()
    await client.call_shv_method(None, "login")
    with pytest.raises(RpcInvalidParamsError):
        await client.read_rpc_message()


async def test_double_mount(shvbroker, url):
    nurl = dataclasses.replace(url, device_mount_point="test/client")
    await SimpleClient.connect(nurl)
    with pytest.raises(RpcMethodCallExceptionError):
        await SimpleClient.connect(nurl)


async def test_sub_mount(shvbroker, url):
    nurl1 = dataclasses.replace(url, device_mount_point="test/client")
    nurl2 = dataclasses.replace(url, device_mount_point="test/client/under")
    await SimpleClient.connect(nurl1)
    with pytest.raises(RpcMethodCallExceptionError):
        await SimpleClient.connect(nurl2)