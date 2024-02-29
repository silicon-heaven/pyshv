"""Check if we correctly emit the lsmod signals."""
import asyncio
import dataclasses

import pytest

from example_device import ExampleDevice
from shv import RpcMessage, RpcSubscription, SimpleClient


class LSClient(SimpleClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lsmods = asyncio.Queue()

    async def _message(self, msg: RpcMessage) -> None:
        await super()._message(msg)
        if msg.is_signal and msg.method == "lsmod":
            await self.lsmods.put((msg.path, msg.param))


@pytest.fixture(name="lsclient")
async def fixture_lsclient(shvbroker, url):
    res = await LSClient.connect(url)
    yield res
    await res.disconnect()


async def test_lsmod(lsclient, url_test_device):
    await lsclient.subscribe(RpcSubscription(signal="lsmod"))

    device = await ExampleDevice.connect(url_test_device)
    assert await lsclient.lsmods.get() == ("", {"test": True})
    lsclient.lsmods.task_done()

    await device.disconnect()
    assert await lsclient.lsmods.get() == ("", {"test": False})
    lsclient.lsmods.task_done()


async def test_lsmod_with_device(shvbroker, lsclient, example_device, url_test_device):
    """Device keeps test path valid and thus we must report it relative to it."""
    await lsclient.subscribe(RpcSubscription(signal="lsmod"))

    nurl = dataclasses.replace(
        url_test_device,
        login=dataclasses.replace(
            url_test_device.login, opt_device_mount_point="test/foo/device"
        ),
    )
    device = await ExampleDevice.connect(nurl)
    assert await lsclient.lsmods.get() == ("test", {"foo": True})
    lsclient.lsmods.task_done()

    cid = (await device.call(".app/broker/currentClient", "info"))["clientId"]
    await shvbroker.mount_client(shvbroker.get_client(cid), "test/other")
    assert await lsclient.lsmods.get() == ("test", {"foo": False, "other": True})
    lsclient.lsmods.task_done()

    await device.disconnect()
    assert await lsclient.lsmods.get() == ("test", {"other": False})
    lsclient.lsmods.task_done()
