"""Check implemntation of SimpleClient."""
import dataclasses

import pytest

from shv import RpcLoginType, RpcMethodSignature, SHVUInt, SimpleClient, shvmeta_eq


@pytest.mark.parametrize(
    "path,method,params,result",
    (
        (".broker/app", "echo", 42, 42),
        ("", "ls", None, [".broker"]),
        (
            "",
            "dir",
            None,
            [
                {
                    "accessGrant": "bws",
                    "flags": SHVUInt(0),
                    "name": "dir",
                    "signature": 3,
                },
                {
                    "accessGrant": "bws",
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
        ("", [".broker"]),
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
        ("", {".broker": True}),
        (
            ".broker",
            {
                "app": True,
                "clients": True,
                "currentClient": False,
                "etc": True,
                "masters": False,
                "mounts": False,
            },
        ),
        (".broker/app/log", {}),
    ),
)
async def test_ls_with_children(client, path, result):
    """Verify that we can use ls_with_children method."""
    res = await client.ls_with_children(path)
    assert res == result


@pytest.mark.parametrize(
    "path,result",
    (
        ("", ["dir", "ls"]),
        (
            ".broker/app/log",
            [
                "dir",
                "ls",
                "chng",
                "getSendLogAsSignalEnabled",
                "setSendLogAsSignalEnabled",
                "verbosity",
                "setVerbosity",
            ],
        ),
    ),
)
async def test_dir(client, path, result):
    """Verify that we can use dir method."""
    res = await client.dir(path)
    assert res == result


@pytest.mark.parametrize(
    "path,result",
    (
        (
            "",
            {
                "dir": {
                    "name": "dir",
                    "signature": RpcMethodSignature.RET_PARAM,
                    "flags": 0,
                    "accessGrant": "bws",
                },
                "ls": {
                    "name": "ls",
                    "signature": RpcMethodSignature.RET_PARAM,
                    "flags": 0,
                    "accessGrant": "bws",
                },
            },
        ),
        (
            ".broker/app/log",
            {
                "chng": {
                    "accessGrant": "rd",
                    "flags": 1,
                    "name": "chng",
                    "signature": 1,
                },
                "dir": {
                    "accessGrant": "bws",
                    "flags": 0,
                    "name": "dir",
                    "signature": 3,
                },
                "getSendLogAsSignalEnabled": {
                    "accessGrant": "rd",
                    "flags": 2,
                    "name": "getSendLogAsSignalEnabled",
                    "signature": 2,
                },
                "ls": {"accessGrant": "rd", "flags": 0, "name": "ls", "signature": 3},
                "setSendLogAsSignalEnabled": {
                    "accessGrant": "wr",
                    "flags": 4,
                    "name": "setSendLogAsSignalEnabled",
                    "signature": 3,
                },
                "setVerbosity": {
                    "accessGrant": "cmd",
                    "flags": 4,
                    "name": "setVerbosity",
                    "signature": 3,
                },
                "verbosity": {
                    "accessGrant": "rd",
                    "flags": 2,
                    "name": "verbosity",
                    "signature": 2,
                },
            },
        ),
    ),
)
async def test_dir_details(client, path, result):
    """Verify that we can use dir method."""
    res = await client.dir_details(path)
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
    assert await client.ls("") == [".broker"]
    await client.disconnect()
