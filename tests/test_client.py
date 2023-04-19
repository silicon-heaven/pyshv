"""Test our RpcClient implementation."""
import pytest


@pytest.mark.asyncio
async def test_broker_echo(client):
    await client.call_shv_method(".broker/app", "echo", 42)
    resp = await client.read_rpc_message()
    assert resp.to_string() == "<1:1,8:3>i{2:42}"


@pytest.mark.asyncio
async def test_broker_ls(client):
    await client.call_shv_method("", "ls")
    resp = await client.read_rpc_message()
    assert resp.result().to_pyrepr() == [".broker"]
