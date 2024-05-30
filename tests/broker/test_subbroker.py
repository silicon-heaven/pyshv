"""Check that we work correctly with subbrokers."""

import asyncio
import dataclasses

import pytest

from example_device import ExampleDevice
from shv import (
    RpcLogin,
    RpcLoginType,
    RpcMessage,
    RpcRI,
    RpcUrl,
    SimpleClient,
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
    subconfig.listen = {"test": suburl}
    subconfig.connection("broker").url.port = port
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
        ("subbroker", "ls", [".app", ".broker", "device"]),
        ("subbroker/device", "ls", [".app", "track"]),
    ),
)
async def test_broker2subbroker(shvbroker, subdevice, client, path, method, result):
    """Check that we correctly access the SHV broker from other broker."""
    assert await client.call(path, method) == result


class NotifClient(SimpleClient):
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

    assert await client.subscribe(RpcRI("subbroker/device/track/**", signal="*chng"))

    assert await client.call(".broker/currentClient", "subscriptions") == [
        {"signal": "*chng", "paths": "subbroker/device/track/**"}
    ]
    assert await client.call("subbroker/.broker/currentClient", "subscriptions") == [
        {"signal": "*chng", "paths": "device/track/**"}
    ]

    await client.call("subbroker/device/track/1", "set", [1])
    assert await client.signals.get() == RpcMessage.signal(
        "subbroker/device/track/1", value=[1]
    )
    client.signals.task_done()

    assert await client.unsubscribe(RpcRI("subbroker/device/track/**", signal="*chng"))
    assert await client.call("subbroker/.broker/currentClient", "subscriptions") == []

    await client.disconnect()
