"""Check implemntation of SimpleClient."""
import dataclasses

import pytest

from shv import (
    RpcLoginType,
    RpcMethodAccess,
    RpcMethodDesc,
    RpcMethodFlags,
    SHVUInt,
    SimpleClient,
    shvmeta_eq,
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
                    "access": "bws",
                    "flags": SHVUInt(0),
                    "name": "dir",
                    "signature": 3,
                },
                {
                    "access": "bws",
                    "flags": SHVUInt(0),
                    "name": "ls",
                    "signature": 3,
                },
            ],
        ),
    ),
)
async def test_call(client, path, method, params, result):
    """Check that we can call various methods using blocking call."""
    res = await client.call(path, method, params)
    assert shvmeta_eq(res, result)


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
    res = await client.ls(path)
    assert res == result


@pytest.mark.parametrize(
    "path,result",
    (
        (
            "",
            [
                RpcMethodDesc("dir"),
                RpcMethodDesc("ls"),
            ],
        ),
        (
            ".broker/app/log",
            [
                RpcMethodDesc("dir"),
                RpcMethodDesc("ls", access=RpcMethodAccess.READ),
                RpcMethodDesc(
                    "chng",
                    RpcMethodFlags.SIGNAL,
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    "getSendLogAsSignalEnabled",
                    RpcMethodFlags.GETTER,
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    "setSendLogAsSignalEnabled",
                    RpcMethodFlags.SETTER,
                    access=RpcMethodAccess.WRITE,
                ),
                RpcMethodDesc(
                    "verbosity",
                    RpcMethodFlags.GETTER,
                    access=RpcMethodAccess.READ,
                ),
                RpcMethodDesc(
                    "setVerbosity",
                    RpcMethodFlags.SETTER,
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


async def test_sha_login(shvbroker, url):
    """Check that we can login with sha1 password.

    Commonly we login with plain password in tests here but we need to check
    ability to login with SHA1 hashed password as well.
    """
    nurl = dataclasses.replace(
        url,
        password="57a261a7bcb9e6cf1db80df501cdd89cee82957e",
        login_type=RpcLoginType.SHA1,
    )
    client = await SimpleClient.connect(nurl)
    assert await client.ls("") == [".broker", "test"]
    await client.disconnect()


async def test_disconnect(client):
    """This tests that multiple calls to disconnect is not an issue."""
    await client.disconnect()
