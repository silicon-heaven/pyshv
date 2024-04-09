"""Check implementation of SimpleClient."""

import contextlib
import dataclasses

import pytest

from shv import (
    RpcLoginType,
    RpcMessage,
    RpcMethodAccess,
    RpcMethodDesc,
    RpcMethodFlags,
    SimpleClient,
    shvmeta,
)


@pytest.mark.parametrize(
    "path,method,params,result",
    (
        (".broker/app", "echo", 42, 42),
        ("", "ls", None, [".broker", "test"]),
        (
            "",
            "dir",
            None,
            [
                {
                    1: "dir",
                    2: 0,
                    3: "DirParam",
                    4: "DirResult",
                    5: 1,
                    6: {},
                    7: {"description": "", "label": ""},
                },
                {
                    1: "ls",
                    2: 0,
                    3: "LsParam",
                    4: "LsResult",
                    5: 1,
                    6: {},
                    7: {"description": "", "label": ""},
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
        ("", [".broker", "test"]),
        (".broker", ["app", "clients", "currentClient", "etc", "masters", "mounts"]),
        (".broker/app/log", []),
    ),
)
async def test_ls(client, path, result):
    """Verify that we can use ls method."""
    assert await client.ls(path) == result


@pytest.mark.parametrize(
    "path,name,result",
    (
        ("", ".broker", True),
        ("", "test", True),
        ("", "invalid", False),
        (".broker", "currentClient", True),
        (".broker", "foo", False),
        (".broker/app", "log", True),
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
            [
                RpcMethodDesc("dir", param="DirParam", result="DirResult"),
                RpcMethodDesc("ls", param="LsParam", result="LsResult"),
            ],
        ),
        (
            ".broker/currentClient",
            [
                RpcMethodDesc("dir", param="DirParam", result="DirResult"),
                RpcMethodDesc("ls", param="LsParam", result="LsResult"),
                RpcMethodDesc(
                    name="clientId",
                    param="Null",
                    result="Int",
                    access=RpcMethodAccess.READ,
                    signals={},
                    extra={},
                ),
                RpcMethodDesc(
                    name="mountPoint",
                    param="Null",
                    result="String",
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    name="userRoles",
                    param="Null",
                    result="List",
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    name="userProfile",
                    param="Null",
                    result="RpcValue",
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    name="accessGrantForMethodCall",
                    param="List",
                    result="String",
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    name="accessLevelForMethodCall",
                    param="List",
                    result="Int",
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    name="accesLevelForMethodCall",
                    param="List",
                    result="Int",
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    name="changePassword",
                    param="List",
                    result="Bool",
                    access=RpcMethodAccess.WRITE,
                ),
            ],
        ),
        (
            ".broker/app/log",
            [
                RpcMethodDesc("dir", param="DirParam", result="DirResult"),
                RpcMethodDesc("ls", param="LsParam", result="LsResult"),
                RpcMethodDesc(
                    "getSendLogAsSignalEnabled",
                    flags=RpcMethodFlags.GETTER,
                    param="Null",
                    result="Bool",
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    "setSendLogAsSignalEnabled",
                    flags=RpcMethodFlags.SETTER,
                    param="Bool",
                    result="Bool",
                    access=RpcMethodAccess.WRITE,
                ),
                RpcMethodDesc(
                    "verbosity",
                    flags=RpcMethodFlags.GETTER,
                    param="Null",
                    result="String",
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    "setVerbosity",
                    flags=RpcMethodFlags.SETTER,
                    param="Bool",
                    result="String",
                    access=RpcMethodAccess.COMMAND,
                ),
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
        (".broker/app", "ping", True),
        (".broker/app", "invalid", False),
        (".broker/currentClient", "clientId", True),
        (".broker/app/log", "verbosity", True),
        (".broker/app/log", "verbositys", False),
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
    client = await SimpleClient.connect(nurl)
    assert await client.ls("") == [".broker", "test"]
    await client.disconnect()


async def test_disconnect(client):
    """Tests that multiple calls to disconnect is not an issue."""
    await client.disconnect()


async def test_reconnect(client):
    """Checks that client reconnects itself if broker disconnects it.

    This uses broker's API to disconnect itself. Broker will give us a new
    client ID and that way we will identify that we successfully reconnected.
    """
    client.reconnects = 2
    cid = await client.call(".broker/currentClient", "clientId")
    # We must use client directly because broker won't respond before it
    # disconnects us and thus we would attempt resent.
    with contextlib.suppress(EOFError):
        await client.client.send(
            RpcMessage.request(f".broker/clients/{cid}", "dropClient")
        )
    assert await client.call(".broker/currentClient", "clientId") != cid
