"""Check that we work correctly with subbrokers."""

import asyncio
import dataclasses

import pytest

from example_device import ExampleDevice
from shv import (
    RpcLogin,
    RpcLoginType,
    RpcMessage,
    RpcUrl,
    SHVClient,
    broker,
)


@pytest.fixture(name="suburl")
def fixture_suburl(unused_tcp_port_factory):
    """URL to connect to the subbroker."""
    return RpcUrl(
        location="localhost",
        port=unused_tcp_port_factory(),
        login=RpcLogin(
            username="admin",
            password="admin!234",
            login_type=RpcLoginType.PLAIN,
        ),
    )


@pytest.fixture(name="shvsubbroker")
async def fixture_shvsubbroker(subconfig, suburl, port, shvbroker):
    subconfig.listen = [suburl]
    subconfig.connect[0].url.port = port
    b = broker.RpcBroker(subconfig)
    await b.start_serving()
    yield b
    await b.terminate()


@pytest.fixture(name="url_subdevice")
def fixture_url_subdevice(suburl):
    return dataclasses.replace(
        suburl,
        login=dataclasses.replace(
            suburl.login,
            username="admin",
            password="admin!234",
            opt_device_mount_point="device",
        ),
    )


@pytest.fixture(name="subdevice")
async def fixture_subdevice(shvsubbroker, url_subdevice):
    """Run example device and provide instance to access it."""
    device = await ExampleDevice.connect(url_subdevice)
    yield device
    await device.disconnect()


@pytest.mark.parametrize(
    "path,method,result",
    (
        ("test/subbroker", "ls", [".app", ".broker", "..", "device"]),
        ("test/subbroker/device", "ls", [".app", "track"]),
    ),
)
async def test_broker2subbroker(shvbroker, subdevice, client, path, method, result):
    """Check that we correctly access the SHV broker from other broker."""
    assert await client.call(path, method) == result


class NotifClient(SHVClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.signals = asyncio.Queue()

    async def _message(self, msg: RpcMessage) -> None:
        await super()._message(msg)
        if msg.is_signal:
            await self.signals.put(msg)


async def test_signal(shvbroker, subdevice, url):
    """Check that we propagate signals through subbroker."""
    client = await NotifClient.connect(url)

    assert await client.subscribe("test/subbroker/device/track/**:*:*chng")
    await asyncio.sleep(0)  # Yield to propagate subscription

    assert await client.call(".broker/currentClient", "subscriptions") == {
        "test/subbroker/device/track/**:*:*chng": None
    }

    subs = await client.call("test/subbroker/.broker/currentClient", "subscriptions")
    assert "device/track/**:*:*chng" in subs

    await client.call("test/subbroker/device/track/1", "set", [1])
    assert await client.signals.get() == RpcMessage.signal(
        "test/subbroker/device/track/1", value=[1]
    )
    client.signals.task_done()

    # Note: unsibscribe happens only after TTL. We do not want to wait so we
    # just don't test it right now.

    await client.disconnect()
