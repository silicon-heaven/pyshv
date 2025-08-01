"""Check if we correctly emit the lsmod signals."""

import asyncio
import dataclasses

import pytest

from example_device import ExampleDevice
from shv.rpcapi.client import SHVClient
from shv.rpcmessage import RpcMessage


class LSClient(SHVClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lsmods = asyncio.Queue()

    async def _message(self, msg: RpcMessage) -> None:
        await super()._message(msg)
        if msg.type is RpcMessage.Type.SIGNAL and msg.method == "lsmod":
            await self.lsmods.put((msg.path, msg.param))


@pytest.fixture(name="lsclient")
async def fixture_lsclient(shvbroker, url):
    res = await LSClient.connect(url)
    yield res
    await res.disconnect()


@pytest.mark.parametrize(
    "mount_point",
    ("test/node", "test/node/well"),
)
async def test_lsmod(lsclient, url_test_device, example_device, mount_point):
    await lsclient.subscribe("**:ls:lsmod")

    nurl = dataclasses.replace(
        url_test_device,
        login=dataclasses.replace(
            url_test_device.login, options={"device": {"mountPoint": mount_point}}
        ),
    )
    device = await ExampleDevice.connect(nurl)
    assert await lsclient.lsmods.get() == ("test", {"node": True})
    lsclient.lsmods.task_done()

    await device.disconnect()
    assert await lsclient.lsmods.get() == ("test", {"node": False})
    lsclient.lsmods.task_done()
