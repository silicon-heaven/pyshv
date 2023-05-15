"""Check that ClientConnection is corectly implemented."""
import collections
import functools

import pytest

from shv import ClientConnection, RpcClient


@pytest.fixture(name="client_connection")
async def fixture_client_connection(shvbroker, port):
    """Instance of CLientConnection connected to the testing broker."""
    client = ClientConnection()
    await client.connect(
        host="localhost",
        port=port,
        user="admin",
        password="admin!123",
        login_type=RpcClient.LoginType.PLAIN,
    )
    yield client
    await client.disconnect()


@pytest.mark.parametrize(
    "path,method,params,result",
    (
        ("", "ls", None, [".broker"]),
        (
            "",
            "dir",
            None,
            [
                {"accessGrant": "bws", "flags": 0, "name": "dir", "signature": 3},
                {"accessGrant": "bws", "flags": 0, "name": "ls", "signature": 3},
            ],
        ),
    ),
)
async def test_call_shv_method_blocking(
    client_connection, path, method, params, result
):
    """Check that we can call various methods using blocking call."""
    msg = await client_connection.call_shv_method_blocking(path, method, params)
    assert msg.result() == result


@pytest.mark.parametrize(
    "paths,updates,expected",
    (
        (
            ("foo", "foo/fee", "foo/fee/faa"),
            {"foo": 1, "foo/fee/faa": 2, "fee": 3},
            {"foo": [("foo", 1)], "foo/fee/faa": [("foo/fee/faa", 2)]},
        ),
        (
            ("foo", "foo/fee"),
            {"foo": 1, "foo/fee/faa": 2},
            {"foo": [("foo", 1)], "foo/fee": [("foo/fee/faa", 2)]},
        ),
    ),
)
def test_update_value_for_path(paths, updates, expected):
    """Check that we can update value using update_value_for_path."""
    values = collections.defaultdict(list)

    def set_value(key, path, value):
        values[key].append((path, value))

    client = ClientConnection()
    for chpath in paths:
        client.set_value_change_handler(chpath, functools.partial(set_value, chpath))
    for path, value in updates.items():
        client.update_value_for_path(path, value)

    assert values == expected
