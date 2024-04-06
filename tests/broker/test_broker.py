"""Check our own implementation of the broker."""

import dataclasses

import pytest

from shv import (
    RpcClientTCP,
    RpcInvalidParamsError,
    RpcLoginRequiredError,
    RpcMessage,
    RpcMethodAccess,
    RpcMethodCallExceptionError,
    RpcMethodDesc,
    RpcMethodNotFoundError,
    RpcSubscription,
    SimpleClient,
    shvmeta,
)


@pytest.mark.parametrize(
    "path,nodes",
    (
        ("", [".app", ".broker"]),
        (".app", []),
        (".broker", ["currentClient", "client"]),
        (".broker/currentClient", []),
        (".broker/client", ["0"]),  # only connection is us
        (".broker/client/0", [".app"]),
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
        ".broker/foo",
        ".broker/client/foo",
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
            [RpcMethodDesc.stddir(), RpcMethodDesc.stdls()],
        ),
        (
            ".app",
            [
                RpcMethodDesc.stddir(),
                RpcMethodDesc.stdls(),
                RpcMethodDesc.getter("shvVersionMajor", "Null", "Int"),
                RpcMethodDesc.getter("shvVersionMinor", "Null", "Int"),
                RpcMethodDesc.getter("name", "Null", "String"),
                RpcMethodDesc.getter("version", "Null", "String"),
                RpcMethodDesc.getter("date", "Null", "DateTime"),
                RpcMethodDesc("ping"),
            ],
        ),
        (
            ".broker",
            [
                RpcMethodDesc.stddir(),
                RpcMethodDesc.stdls(),
                RpcMethodDesc("clientInfo", access=RpcMethodAccess.SUPER_SERVICE),
                RpcMethodDesc(
                    "mountedClientInfo", access=RpcMethodAccess.SUPER_SERVICE
                ),
                RpcMethodDesc.getter("clients", access=RpcMethodAccess.SUPER_SERVICE),
                RpcMethodDesc.getter("mounts", access=RpcMethodAccess.SUPER_SERVICE),
                RpcMethodDesc("disconnectClient", access=RpcMethodAccess.SUPER_SERVICE),
            ],
        ),
        (
            ".broker/currentClient",
            [
                RpcMethodDesc.stddir(),
                RpcMethodDesc.stdls(),
                RpcMethodDesc.getter("info", access=RpcMethodAccess.BROWSE),
                RpcMethodDesc("subscribe", access=RpcMethodAccess.BROWSE),
                RpcMethodDesc("unsubscribe", access=RpcMethodAccess.BROWSE),
                RpcMethodDesc.getter("subscriptions", access=RpcMethodAccess.BROWSE),
            ],
        ),
        (
            ".broker/client",
            [RpcMethodDesc.stddir(), RpcMethodDesc.stdls()],
        ),
    ),
)
async def test_empty_dir(client, path, methods):
    """Check tree provided by empty broker."""
    assert await client.dir(path) == methods


@pytest.mark.parametrize(
    "path,method,param,result",
    (
        (".broker", "clients", None, [0]),
        (".broker", "mounts", None, []),
        (
            ".broker",
            "clientInfo",
            0,
            {
                "clientId": 0,
                "mountPoint": None,
                "subscriptions": [],
                "userName": "admin",
                "idleTime": 0,
                "idleTimeMax": 180000,
            },
        ),
        (".broker", "mountedClientInfo", "test", None),
        (
            ".broker/currentClient",
            "info",
            None,
            {
                "clientId": 0,
                "mountPoint": None,
                "subscriptions": [],
                "userName": "admin",
                "idleTime": 0,
                "idleTimeMax": 180000,
            },
        ),
        (".broker/currentClient", "subscriptions", None, []),
        (".broker/client/0/.app", "name", None, "pyshv-client"),
    ),
)
async def test_empty_call(client, path, method, param, result):
    """Call various broker methods."""
    res = await client.call(path, method, param)
    assert res == result
    assert shvmeta(res) == shvmeta(result)


@pytest.mark.parametrize(
    "path,nodes",
    (
        (".broker/client", ["0", "1"]),
        ("", [".app", ".broker", "test"]),
        ("test", ["device"]),
        ("test/device", [".app", "track"]),
        ("test/device/track", ["1", "2", "3", "4", "5", "6", "7", "8"]),
    ),
)
async def test_with_example_ls(client, example_device, path, nodes):
    assert await client.ls(path) == nodes


@pytest.mark.parametrize(
    "param,result",
    (
        (
            "test/device",
            {
                "clientId": 1,
                "mountPoint": "test/device",
                "subscriptions": [],
                "userName": "test",
                "idleTime": 42,
                "idleTimeMax": 180000,
            },
        ),
        (
            "test/device/track",
            {
                "clientId": 1,
                "mountPoint": "test/device",
                "subscriptions": [],
                "userName": "test",
                "idleTime": 42,
                "idleTimeMax": 180000,
            },
        ),
    ),
)
async def test_mounted_client_info(client, example_device, param, result):
    res = await client.call(".broker", "mountedClientInfo", param)
    assert res["idleTime"] >= 0
    res["idleTime"] = 42
    assert res == result
    assert shvmeta(res) == shvmeta(result)


async def test_subscribe(client, example_device):
    sub = RpcSubscription("test/device/track/**")
    assert await client.subscribe(sub) is True
    assert await client.subscribe(sub) is False
    assert await client.call(".broker/currentClient", "subscriptions") == [
        {"paths": "test/device/track/**"}
    ]
    assert await client.unsubscribe(sub) is True
    assert await client.call(".broker/currentClient", "subscriptions") == []
    assert await client.unsubscribe(sub) is False


async def test_with_example_set(example_device, value_client):
    """Perform set to trigger also notifications."""
    await value_client.subscribe(RpcSubscription("test/device/track/**"))
    await value_client.prop_set("test/device/track/1", [1, 2])
    assert await value_client.prop_get("test/device/track/1") == [1, 2]
    assert value_client["test/device/track/1"] == [1, 2]


async def test_with_example_reset(example_device, client):
    """Perform reset on example device to check user's ID."""
    await client.call("test/device/track", "reset")
    assert await client.call("test/device/track", "lastResetUser") == "testbroker:admin"


async def test_unauthorized_access(shvbroker, value_client):
    """Check that we are not allowed to access node we do not have access to."""
    with pytest.raises(RpcMethodNotFoundError):
        await value_client.call(".broker/clients/0", "userName")


async def test_invalid_login(shvbroker, url):
    nurl = dataclasses.replace(
        url, login=dataclasses.replace(url.login, password="invalid")
    )
    with pytest.raises(RpcMethodCallExceptionError, match="Invalid login"):
        await SimpleClient.connect(nurl)


async def test_invalid_hello_seq(shvbroker, url):
    client = await RpcClientTCP.connect(url.location, url.port)
    await client.send(RpcMessage.request(None, "invalid"))
    with pytest.raises(RpcLoginRequiredError, match=r"Use hello method"):
        await client.receive()


async def test_invalid_login_seq(shvbroker, url):
    client = await RpcClientTCP.connect(url.location, url.port)
    await client.send(RpcMessage.request(None, "hello"))
    await client.receive()
    await client.send(RpcMessage.request(None, "invalid"))
    with pytest.raises(RpcLoginRequiredError, match=r"Use hello and login methods"):
        await client.receive()


async def test_invalid_login_null(shvbroker, url):
    client = await RpcClientTCP.connect(url.location, url.port)
    await client.send(RpcMessage.request(None, "hello"))
    await client.receive()
    await client.send(RpcMessage.request(None, "login"))
    with pytest.raises(RpcInvalidParamsError):
        await client.receive()


async def test_double_mount(shvbroker, url):
    nurl = dataclasses.replace(
        url, login=dataclasses.replace(url.login, opt_device_mount_point="test/client")
    )
    c = await SimpleClient.connect(nurl)
    with pytest.raises(RpcMethodCallExceptionError):
        await SimpleClient.connect(nurl)
    await c.disconnect()


async def test_sub_mount(shvbroker, url):
    nurl1 = dataclasses.replace(
        url, login=dataclasses.replace(url.login, opt_device_mount_point="test/client")
    )
    nurl2 = dataclasses.replace(
        url,
        login=dataclasses.replace(
            url.login, opt_device_mount_point="test/client/under"
        ),
    )
    c = await SimpleClient.connect(nurl1)
    with pytest.raises(RpcMethodCallExceptionError):
        await SimpleClient.connect(nurl2)
    await c.disconnect()


async def test_client_reset(client):
    """Check that client can reset its connection and login again.

    After reconnection client must always have unique ID and thus we deteect
    only that.
    """
    cid = await client.call(".broker/currentClient", "info")
    await client.reset()
    assert (await client.call(".broker/currentClient", "info"))["clientId"] != cid[
        "clientId"
    ]


async def test_broker_client(example_device, shvbroker):
    """Check that we can use broker's clients as clients as well."""
    client = next(shvbroker.clients())
    assert await client.call(".app", "name") == "pyshv-example_device"


# TODO test clients disconnect on idle
# TODO test access level
