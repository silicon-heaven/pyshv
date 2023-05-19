"""Check implemntation of SimpleClient."""
import collections
import functools

import pytest

from shv import RpcClient, SHVUInt, SimpleClient, shvmeta_eq


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
