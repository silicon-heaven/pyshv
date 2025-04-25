"""Check implementation of SHVClient."""

import asyncio
import dataclasses

import pytest

from shv import (
    RpcAccess,
    RpcDir,
    RpcLoginType,
    SHVClient,
    shvmeta,
)


@pytest.mark.parametrize(
    "path,method,params,result",
    (
        (".app", "ping", None, None),
        ("", "ls", None, [".app", ".broker"]),
        (
            "",
            "dir",
            None,
            [
                {
                    1: "dir",
                    2: 0,
                    3: "n|b|s",
                    4: "[!dir]|b",
                    5: 1,
                },
                {
                    1: "ls",
                    2: 0,
                    3: "s|n",
                    4: "[s]|b",
                    5: 1,
                    6: {"lsmod": "{b}"},
                },
            ],
        ),
    ),
)
async def test_call(client, path, method, params, result):
    """Check that we can call various methods using blocking call."""
    res = await client.call(path, method, params)
    assert res == result
    assert shvmeta(res) == shvmeta(result)


@pytest.mark.parametrize(
    "path,result",
    (
        ("", [".app", ".broker"]),
        (".app", []),
        (".broker", ["currentClient", "client"]),
    ),
)
async def test_ls(client, path, result):
    """Verify that we can use ls method."""
    assert await client.ls(path) == result


@pytest.mark.parametrize(
    "path,name,result",
    (
        ("", ".broker", True),
        ("", "invalid", False),
        (".broker", "currentClient", True),
        (".broker", "foo", False),
    ),
)
async def test_ls_has_child(client, path, name, result):
    """Verify that child existence check works."""
    assert await client.ls_has_child(path, name) == result


@pytest.mark.parametrize(
    "path,result",
    (
        (
            "",
            [RpcDir.stddir(), RpcDir.stdls()],
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
                RpcDir("info", RpcDir.Flag.GETTER, result="!clientInfo"),
                RpcDir("subscribe", param="s|[s:RPCRI,i:TTL]", result="b"),
                RpcDir("unsubscribe", param="s", result="b"),
                RpcDir.getter("subscriptions", result="{i|n}", access=RpcAccess.BROWSE),
            ],
        ),
    ),
)
async def test_dir(client, path, result):
    """Verify that we can use dir method."""
    res = await client.dir(path)
    assert res == result


@pytest.mark.parametrize(
    "path,name,result",
    (
        (".app", "ping", True),
        (".app", "invalid", False),
        (".broker/currentClient", "info", True),
    ),
)
async def test_dir_exists(client, path, name, result):
    """Verify that method existence check works."""
    res = await client.dir_exists(path, name)
    assert res == result


async def test_sha_login(shvbroker, url):
    """Check that we can login with sha1 password.

    Commonly we login with plain password in tests here but we need to check
    ability to login with SHA1 hashed password as well.
    """
    nurl = dataclasses.replace(
        url,
        login=dataclasses.replace(
            url.login,
            password="57a261a7bcb9e6cf1db80df501cdd89cee82957e",
            login_type=RpcLoginType.SHA1,
        ),
    )
    client = await SHVClient.connect(nurl)
    assert await client.call(".app", "ping") is None
    await client.disconnect()


async def test_disconnect(client):
    """Tests that multiple calls to disconnect is not an issue."""
    await client.disconnect()


async def test_reconnect(client, shvbroker):
    """Checks that client reconnects itself if broker disconnects it.

    This uses broker's API to disconnect itself. Broker will give us a new
    client ID and that way we will identify that we successfully reconnected.
    """
    client.reconnects = 2
    info = await client.call(".broker/currentClient", "info")
    await shvbroker.get_client(info["clientId"]).disconnect()
    await asyncio.sleep(0)
    assert (await client.call(".broker/currentClient", "info"))["clientId"] != info[
        "clientId"
    ]
