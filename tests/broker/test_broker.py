"""Check our own implementation of the broker."""

import dataclasses

import pytest

from shv import (
    RpcAccess,
    RpcDir,
    RpcInvalidParamError,
    RpcLoginRequiredError,
    RpcMessage,
    RpcMethodCallExceptionError,
    RpcMethodNotFoundError,
    SHVClient,
    shvmeta,
)
from shv.rpctransport import RpcClientTCP


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
            [RpcDir.stddir(), RpcDir.stdls()],
        ),
        (
            ".app",
            [
                RpcDir.stddir(),
                RpcDir.stdls(),
                RpcDir.getter("shvVersionMajor", "n", "i"),
                RpcDir.getter("shvVersionMinor", "n", "i"),
                RpcDir.getter("name", "n", "s"),
                RpcDir.getter("version", "n", "s"),
                RpcDir.getter("date", "n", "t"),
                RpcDir("ping"),
            ],
        ),
        (
            ".broker",
            [
                RpcDir.stddir(),
                RpcDir.stdls(),
                RpcDir.getter("name", "n", "s", access=RpcAccess.BROWSE),
                RpcDir(
                    "clientInfo",
                    param="i",
                    result="!clientInfo|n",
                    access=RpcAccess.SUPER_SERVICE,
                ),
                RpcDir(
                    "mountedClientInfo",
                    param="s",
                    result="!clientInfo|n",
                    access=RpcAccess.SUPER_SERVICE,
                ),
                RpcDir.getter("clients", "n", "[i]", access=RpcAccess.SUPER_SERVICE),
                RpcDir.getter("mounts", "n", "[s]", access=RpcAccess.SUPER_SERVICE),
                RpcDir("disconnectClient", param="i", access=RpcAccess.SUPER_SERVICE),
            ],
        ),
        (
            ".broker/currentClient",
            [
                RpcDir.stddir(),
                RpcDir.stdls(),
                RpcDir(
                    "info",
                    RpcDir.Flag.GETTER,
                    result="!clientInfo",
                    access=RpcAccess.BROWSE,
                ),
                RpcDir(
                    "subscribe",
                    param="s|[s:RPCRI,i:TTL]",
                    result="b",
                    access=RpcAccess.BROWSE,
                ),
                RpcDir("unsubscribe", param="s", result="b", access=RpcAccess.BROWSE),
                RpcDir.getter("subscriptions", result="{i|n}", access=RpcAccess.BROWSE),
            ],
        ),
        (
            ".broker/client",
            [RpcDir.stddir(), RpcDir.stdls()],
        ),
    ),
)
async def test_empty_dir(client, path, methods):
    """Check tree provided by empty broker."""
    assert await client.dir(path) == methods


@pytest.mark.parametrize(
    "path,method,param,result",
    (
        (".broker", "name", None, "testbroker"),
        (".broker", "clients", None, [0]),
        (".broker", "mounts", None, []),
        (".broker/currentClient", "subscriptions", None, {}),
        (".broker/client/0/.app", "name", None, "pyshv-client"),
    ),
)
async def test_empty_call(client, path, method, param, result):
    """Call various broker methods."""
    res = await client.call(path, method, param)
    assert res == result
    assert shvmeta(res) == shvmeta(result)


@pytest.mark.parametrize(
    "path,method,param,result",
    (
        (
            ".broker",
            "clientInfo",
            0,
            {
                # "client": indeterministic
                "clientId": 0,
                "deviceId": None,
                "mountPoint": None,
                "subscriptions": {},
                "userName": "admin",
                "role": "admin",
                # "idleTime": indeterministic
                "idleTimeMax": 180000,
            },
        ),
        (
            ".broker/currentClient",
            "info",
            None,
            {
                # "client": indeterministic
                "clientId": 0,
                "deviceId": None,
                "mountPoint": None,
                "subscriptions": {},
                "userName": "admin",
                "role": "admin",
                # "idleTime": indeterministic
                "idleTimeMax": 180000,
            },
        ),
    ),
)
async def test_client_info(client, path, method, param, result):
    """Call client info query methods."""
    res = await client.call(path, method, param)
    assert res["client"]
    del res["client"]
    assert isinstance(res["idleTime"], int)
    assert res["idleTime"] >= 0
    del res["idleTime"]
    assert res == result
    assert shvmeta(res) == shvmeta(result)


@pytest.mark.parametrize(
    "path,nodes",
    (
        (".broker/client", ["0", "1"]),
        ("", [".app", ".broker", "test"]),
        ("test", ["device"]),
        ("test/device", [".app", "numberOfTracks", "track"]),
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
                # "client": indeterministic
                "clientId": 1,
                "deviceId": "example",
                "mountPoint": "test/device",
                "subscriptions": {},
                "userName": "test",
                "role": "test-browse",
                # "idleTime": indeterministic
                "idleTimeMax": 180000,
            },
        ),
        (
            "test/device/track",
            {
                # "client": indeterministic
                "clientId": 1,
                "deviceId": "example",
                "mountPoint": "test/device",
                "subscriptions": {},
                "userName": "test",
                "role": "test-browse",
                # "idleTime": indeterministic
                "idleTimeMax": 180000,
            },
        ),
    ),
)
async def test_mounted_client_info(client, example_device, param, result):
    res = await client.call(".broker", "mountedClientInfo", param)
    assert res["idleTime"] >= 0
    del res["idleTime"]
    assert res["client"]
    assert isinstance(res["client"], str)
    del res["client"]
    assert res == result
    assert shvmeta(res) == shvmeta(result)


async def test_subscribe(client, example_device):
    sub = "test/device/track/**:*:*"
    assert await client.subscribe(sub) is True
    assert await client.subscribe(sub) is False
    assert await client.call(".broker/currentClient", "subscriptions") == {
        "test/device/track/**:*:*": None
    }
    assert await client.unsubscribe(sub) is True
    assert await client.call(".broker/currentClient", "subscriptions") == {}
    assert await client.unsubscribe(sub) is False


async def test_with_example_set(example_device, value_client):
    """Perform set to trigger also notifications."""
    await value_client.subscribe("test/device/track/**:*:*")
    await value_client.prop_set("test/device/track/1", [1, 2])
    assert await value_client.prop_get("test/device/track/1") == [1, 2]
    assert value_client["test/device/track/1"] == [1, 2]


async def test_with_example_reset(example_device, client):
    """Perform reset on example device to check user's ID."""
    await client.call("test/device/track", "reset")
    assert await client.call("test/device/track", "lastResetUser") == "admin:testbroker"


async def test_unauthorized_access(shvbroker, value_client):
    """Check that we are not allowed to access node we do not have access to."""
    with pytest.raises(RpcMethodNotFoundError):
        await value_client.call(".broker/clients/0", "userName")


async def test_invalid_login(shvbroker, url):
    nurl = dataclasses.replace(
        url, login=dataclasses.replace(url.login, password="invalid")
    )
    with pytest.raises(RpcMethodCallExceptionError, match="Invalid login"):
        await SHVClient.connect(nurl)


async def test_invalid_hello_seq(shvbroker, url):
    client = await RpcClientTCP.connect(url.location, url.port)
    await client.send(RpcMessage.request("", "invalid"))
    with pytest.raises(RpcLoginRequiredError, match=r"Use login method"):
        raise (await client.receive()).error


async def test_invalid_login_null(shvbroker, url):
    client = await RpcClientTCP.connect(url.location, url.port)
    await client.send(RpcMessage.request("", "hello"))
    await client.receive()
    await client.send(RpcMessage.request("", "login"))
    with pytest.raises(RpcInvalidParamError):
        raise (await client.receive()).error


async def test_double_mount(shvbroker, url):
    nurl = dataclasses.replace(
        url, login=dataclasses.replace(url.login, opt_device_mount_point="test/client")
    )
    c = await SHVClient.connect(nurl)
    with pytest.raises(RpcMethodCallExceptionError):
        await SHVClient.connect(nurl)
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
    c = await SHVClient.connect(nurl1)
    with pytest.raises(RpcMethodCallExceptionError):
        await SHVClient.connect(nurl2)
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


# TODO test clients disconnect on idle
# TODO test access level
# TODO test subscription TTL
