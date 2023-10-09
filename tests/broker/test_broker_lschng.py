"""Check if we correctly emit the lschng signals."""
import asyncio
import dataclasses

import pytest

from example_device import ExampleDevice
from shv import RpcMessage, SimpleClient


class LSClient(SimpleClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lschanges = []

    async def _message(self, msg: RpcMessage) -> None:
        await super()._message(msg)
        if msg.is_signal() and msg.method() == "lschng":
            self.lschanges.append((msg.shv_path(), msg.param()))

    def poplschng(self):
        res = self.lschanges
        self.lschanges = []
        return res


@pytest.fixture(name="lsclient")
async def fixture_lsclient(shvbroker, url):
    res = await LSClient.connect(url)
    yield res
    await res.disconnect()


async def test_lschng(lsclient, url_test_device):
    await lsclient.subscribe("", "lschng")

    device = await ExampleDevice.connect(url_test_device)
    await asyncio.sleep(0)  # Await for receive
    assert lsclient.poplschng() == [("", {"test": True})]

    await device.disconnect()
    await asyncio.sleep(0.1)  # Await for receive
    assert lsclient.poplschng() == [("", {"test": False})]


async def test_lschng_with_device(shvbroker, lsclient, example_device, url_test_device):
    """Device keeps test path valid and thus we must report it relative to it."""
    await lsclient.subscribe("", "lschng")

    nurl = dataclasses.replace(url_test_device, device_mount_point="test/foo/device")
    device = await ExampleDevice.connect(nurl)
    await asyncio.sleep(0)  # Await for receive
    assert lsclient.poplschng() == [("test", {"foo": True})]

    cid = (await device.call(".app/broker/currentClient", "info"))["clientId"]
    await shvbroker.clients[cid].set_mount_point("test/other")
    await asyncio.sleep(0.1)  # Await for receive
    assert lsclient.poplschng() == [("test", {"foo": False, "other": True})]

    await device.disconnect()
    await asyncio.sleep(0.1)  # Await for receive
    assert lsclient.poplschng() == [("test", {"other": False})]
