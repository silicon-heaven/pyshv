"""Check our own implementation of the broker."""
import dataclasses

import pytest

from shv import (
    RpcClientStream,
    RpcInvalidParamsError,
    RpcInvalidRequestError,
    RpcMessage,
    RpcMethodAccess,
    RpcMethodCallExceptionError,
    RpcMethodDesc,
    RpcMethodNotFoundError,
    SimpleClient,
    shvmeta_eq,
)


@pytest.mark.parametrize(
    "path,nodes",
    (
        ("", [".app"]),
        (".app", ["broker"]),
        (".app/broker", ["currentClient", "client", "clientInfo"]),
        (".app/broker/currentClient", []),
        (".app/broker/client", ["0"]),  # only connection is us
        (".app/broker/client/0", [".app"]),
        (".app/broker/clientInfo", ["0"]),  # only connection is us
        (".app/broker/clientInfo/0", []),
    ),
)
async def test_empty_ls(client, path, nodes):
    """Check tree provided by empty broker."""
    assert await client.ls(path) == nodes


@pytest.mark.parametrize(
    "path",
    (
        "foo",
        ".app/foo",
        ".app/broker/foo",
        ".app/broker/client/foo",
    ),
)
async def test_empty_ls_invalid(client, path):
    """Check tree provided by empty broker."""
    with pytest.raises(RpcMethodNotFoundError):
        await client.ls(path)


@pytest.mark.parametrize(
    "path,methods",
    (
        (
            "",
            [
                RpcMethodDesc("dir", param="idir", result="odir"),
                RpcMethodDesc("ls", param="ils", result="ols"),
                RpcMethodDesc.signal("lschng", "olschng", RpcMethodAccess.BROWSE),
            ],
        ),
        (
            ".app",
            [
                RpcMethodDesc("dir", param="idir", result="odir"),
                RpcMethodDesc("ls", param="ils", result="ols"),
                RpcMethodDesc.signal("lschng", "olschng", RpcMethodAccess.BROWSE),
                RpcMethodDesc.getter("shvVersionMajor", "Null", "Int"),
                RpcMethodDesc.getter("shvVersionMinor", "Null", "Int"),
                RpcMethodDesc.getter("name", "Null", "String"),
                RpcMethodDesc.getter("version", "Null", "String"),
                RpcMethodDesc("ping"),
            ],
        ),
        (
            ".app/broker",
            [
                RpcMethodDesc("dir", param="idir", result="odir"),
                RpcMethodDesc("ls", param="ils", result="ols"),
                RpcMethodDesc.signal("lschng", "olschng", RpcMethodAccess.BROWSE),
                RpcMethodDesc("clientInfo", access=RpcMethodAccess.SERVICE),
                RpcMethodDesc.getter("clients", access=RpcMethodAccess.SERVICE),
                RpcMethodDesc("disconnectClient", access=RpcMethodAccess.SERVICE),
                RpcMethodDesc.getter("mountPoints", access=RpcMethodAccess.READ),
            ],
        ),
        (
            ".app/broker/currentClient",
            [
                RpcMethodDesc("dir", param="idir", result="odir"),
                RpcMethodDesc("ls", param="ils", result="ols"),
                RpcMethodDesc.signal("lschng", "olschng", RpcMethodAccess.BROWSE),
                RpcMethodDesc.getter("info", access=RpcMethodAccess.BROWSE),
                RpcMethodDesc("subscribe", access=RpcMethodAccess.READ),
                RpcMethodDesc("unsubscribe", access=RpcMethodAccess.READ),
                RpcMethodDesc("rejectNotSubscribed", access=RpcMethodAccess.READ),
                RpcMethodDesc.getter("subscriptions", access=RpcMethodAccess.READ),
            ],
        ),
        (
            ".app/broker/client",
            [
                RpcMethodDesc("dir", param="idir", result="odir"),
                RpcMethodDesc("ls", param="ils", result="ols"),
                RpcMethodDesc.signal("lschng", "olschng", RpcMethodAccess.BROWSE),
            ],
        ),
        (
            ".app/broker/clientInfo/0",
            [
                RpcMethodDesc("dir", param="idir", result="odir"),
                RpcMethodDesc("ls", param="ils", result="ols"),
                RpcMethodDesc.signal("lschng", "olschng", RpcMethodAccess.BROWSE),
                RpcMethodDesc.getter("userName", "String"),
                RpcMethodDesc.getter("mountPoint", "String"),
                RpcMethodDesc.getter("subscriptions"),
                RpcMethodDesc("dropClient", access=RpcMethodAccess.SERVICE),
                RpcMethodDesc.getter("idleTime"),
                RpcMethodDesc.getter("idleTimeMax"),
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
        (".app/broker", "mountPoints", []),
        (
            ".app/broker/currentClient",
            "info",
            {
                "clientId": 0,
                "mountPoint": None,
                "subscriptions": [],
                "userName": "admin",
            },
        ),
        (".app/broker/currentClient", "subscriptions", []),
        (".app/broker/client/0/.app", "name", "pyshv"),
        (".app/broker/clientInfo/0", "userName", "admin"),
        (".app/broker/clientInfo/0", "mountPoint", None),
        (".app/broker/clientInfo/0", "subscriptions", []),
        (".app/broker/clientInfo/0", "idleTime", 0),  # we are the one asking
        (".app/broker/clientInfo/0", "idleTimeMax", 180000),
    ),
)
async def test_empty_call(client, path, method, result):
    """Call various broker methods."""
    assert shvmeta_eq(await client.call(path, method), result)


@pytest.mark.parametrize(
    "path,nodes",
    (
        (".app/broker/client", ["0", "1"]),
        ("", [".app", "test"]),
        ("test/device", [".app", "track"]),
        ("test/device/track", ["1", "2", "3", "4", "5", "6", "7", "8"]),
    ),
)
async def test_with_example_ls(client, example_device, path, nodes):
    assert await client.ls(path) == nodes


async def test_subscribe(client, example_device):
    await client.subscribe("test/device/track")
    assert await client.call(".app/broker/currentClient", "subscriptions") == [
        {"method": "chng", "path": "test/device/track"}
    ]
    assert await client.unsubscribe("test/device/track") is True
    assert await client.call(".app/broker/currentClient", "subscriptions") == []
    assert await client.unsubscribe("test/device/track") is False


async def test_reject_not_subscribed(client, example_device):
    await client.subscribe("test/device/track")
    assert (
        await client.call(
            ".app/broker/currentClient",
            "rejectNotSubscribed",
            {"path": "no/such/node"},
        )
        == []
    )
    assert await client.call(
        ".app/broker/currentClient",
        "rejectNotSubscribed",
        {"path": "test/device/track/1", "method": "chng"},
    ) == [{"path": "test/device/track", "method": "chng"}]


async def test_with_example_set(example_device, value_client):
    """Perform set to trigger also notifications."""
    await value_client.subscribe("test/device/track")
    await value_client.prop_set("test/device/track/1", [1, 2])
    assert await value_client.prop_get("test/device/track/1") == [1, 2]
    assert value_client["test/device/track/1"] == [1, 2]


async def test_unauthorized_access(shvbroker, value_client):
    """Check that we are not allowed to access node we do not have access to."""
    with pytest.raises(RpcMethodNotFoundError):
        await value_client.call(".app/broker/clients/0", "userName")


async def test_invalid_login(shvbroker, url):
    nurl = dataclasses.replace(url, password="invalid")
    with pytest.raises(RpcMethodCallExceptionError):
        await SimpleClient.connect(nurl)


async def test_invalid_hello_seq(shvbroker, url):
    client = await RpcClientStream.connect(url.location, url.port)
    await client.send(RpcMessage.request(None, "invalid"))
    with pytest.raises(RpcInvalidRequestError):
        await client.receive()


async def test_invalid_login_seq(shvbroker, url):
    client = await RpcClientStream.connect(url.location, url.port)
    await client.send(RpcMessage.request(None, "hello"))
    await client.receive()
    await client.send(RpcMessage.request(None, "invalid"))
    with pytest.raises(RpcInvalidRequestError):
        await client.receive()


async def test_invalid_login_null(shvbroker, url):
    client = await RpcClientStream.connect(url.location, url.port)
    await client.send(RpcMessage.request(None, "hello"))
    await client.receive()
    await client.send(RpcMessage.request(None, "login"))
    with pytest.raises(RpcInvalidParamsError):
        await client.receive()


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


async def test_broker_client(example_device, shvbroker):
    """Check that we can use broker's clients as clients as well."""
    client = shvbroker.clients[0]
    assert await client.call(".app", "name") == "pyshv-example_device"
