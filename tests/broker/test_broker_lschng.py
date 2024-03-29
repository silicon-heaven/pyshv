"""Check if we correctly emit the lschng signals."""
import asyncio
import dataclasses

import pytest

from example_device import ExampleDevice
from shv import RpcMessage, RpcSubscription, SimpleClient


class LSClient(SimpleClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lschngs = asyncio.Queue()

    async def _message(self, msg: RpcMessage) -> None:
        await super()._message(msg)
        if msg.is_signal and msg.method == "lschng":
            await self.lschngs.put((msg.path, msg.param))


@pytest.fixture(name="lsclient")
async def fixture_lsclient(shvbroker, url):
    res = await LSClient.connect(url)
    yield res
    await res.disconnect()


async def test_lschng(lsclient, url_test_device):
    await lsclient.subscribe(RpcSubscription("", "lschng"))

    device = await ExampleDevice.connect(url_test_device)
    assert await lsclient.lschngs.get() == ("", {"test": True})
    lsclient.lschngs.task_done()

    await device.disconnect()
    assert await lsclient.lschngs.get() == ("", {"test": False})
    lsclient.lschngs.task_done()


async def test_lschng_with_device(shvbroker, lsclient, example_device, url_test_device):
    """Device keeps test path valid and thus we must report it relative to it."""
    await lsclient.subscribe(RpcSubscription("", "lschng"))

    nurl = dataclasses.replace(
        url_test_device,
        login=dataclasses.replace(
            url_test_device.login, opt_device_mount_point="test/foo/device"
        ),
    )
    device = await ExampleDevice.connect(nurl)
    assert await lsclient.lschngs.get() == ("test", {"foo": True})
    lsclient.lschngs.task_done()

    cid = (await device.call(".app/broker/currentClient", "info"))["clientId"]
    await shvbroker.clients[cid].set_mount_point("test/other")
    assert await lsclient.lschngs.get() == ("test", {"foo": False, "other": True})
    lsclient.lschngs.task_done()

    await device.disconnect()
    assert await lsclient.lschngs.get() == ("test", {"other": False})
    lsclient.lschngs.task_done()
