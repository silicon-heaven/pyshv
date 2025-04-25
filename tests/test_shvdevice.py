"""Check implementation of SimpleDevice."""

import datetime
import time

import pytest

from shv import (
    SHV_VERSION_MAJOR,
    SHV_VERSION_MINOR,
    VERSION,
    RpcAccess,
    RpcAlert,
    RpcDir,
    RpcMethodNotFoundError,
    RpcNotImplementedError,
    SHVDevice,
    shvmeta,
)


class Device(SHVDevice):
    DEVICE_NAME = "testdev"
    DEVICE_VERSION = "0.0.x"


@pytest.fixture(name="device")
async def fixture_device(shvbroker, url_test_device):
    """Run device and provide instance to access it."""
    device = await Device.connect(url_test_device)
    yield device
    await device.disconnect()


@pytest.mark.parametrize(
    "path,method,result",
    (
        ("test/device/.app", "shvVersionMajor", SHV_VERSION_MAJOR),
        ("test/device/.app", "shvVersionMinor", SHV_VERSION_MINOR),
        ("test/device/.app", "name", "pyshv-device"),
        ("test/device/.app", "version", VERSION),
        ("test/device/.app", "ping", None),
        ("test/device/.device", "name", "testdev"),
        ("test/device/.device", "version", "0.0.x"),
        ("test/device/.device", "serialNumber", None),
    ),
)
async def test_call(client, device, path, method, result):
    """Check that we can call various methods using blocking call."""
    res = await client.call(path, method)
    assert res == result
    assert shvmeta(res) == shvmeta(result)


async def test_call_date(client, device):
    """Check that we can call various methods using blocking call."""
    res = await client.call("test/device/.app", "date")
    assert isinstance(res, datetime.datetime)
    assert res.tzinfo is not None
    diff = datetime.datetime.now().astimezone() - res
    assert datetime.timedelta() <= diff < datetime.timedelta(seconds=1)


async def test_invalid_call(client):
    with pytest.raises(RpcMethodNotFoundError):
        await client.call(".app", "someInvalid")


@pytest.mark.parametrize(
    "path,result",
    (
        ("test/device", [".app", ".device"]),
        ("test/device/.app", []),
        ("test/device/.device", ["alerts"]),
        ("test/device/.device/alerts", []),
    ),
)
async def test_ls(client, device, path, result):
    """Verify that we can use ls method."""
    res = await client.ls(path)
    assert res == result


@pytest.mark.parametrize(
    "path,result",
    (
        (
            "test/device/.device",
            [
                RpcDir.stddir(),
                RpcDir.stdls(),
                RpcDir.getter("name", "n", "s", access=RpcAccess.BROWSE),
                RpcDir.getter("version", "n", "s", access=RpcAccess.BROWSE),
                RpcDir.getter("serialNumber", "n", "s|n", access=RpcAccess.BROWSE),
                RpcDir.getter("uptime", "n", "u|n", access=RpcAccess.BROWSE),
                RpcDir("reset", access=RpcAccess.COMMAND),
            ],
        ),
        (
            "test/device/.device/alerts",
            [
                RpcDir.stddir(),
                RpcDir.stdls(),
                RpcDir.getter(result="[!alert]", signal=True),
            ],
        ),
    ),
)
async def test_dir(client, device, path, result):
    """Verify that we can use dir method."""
    res = await client.dir(path)
    assert res == result


async def test_reset(client, device):
    """Check if reset can be called and we get the not implemented error."""
    with pytest.raises(RpcNotImplementedError):
        await client.call("test/device/.device", "reset")


async def test_uptime(client, device):
    """We can't test uptime in general but at least be reasonable with it."""
    uptime = int(time.monotonic())
    assert await client.call("test/device/.device", "uptime") >= uptime


async def test_alerts(value_client, device):
    """Check that we correctly manage alerts."""
    await value_client.subscribe("test/device/.device/alerts:get:chng")
    assert await value_client.prop_get("test/device/.device/alerts") == []

    now1 = datetime.datetime.now().replace(microsecond=0, tzinfo=datetime.UTC)
    test1 = RpcAlert.new(RpcAlert.WARNING_MIN, "Test1", now1)
    change = value_client.wait_for_change("test/device/.device/alerts")
    await device.change_alerts()  # Just to ensure that we do not send signal
    await device.change_alerts(add=test1)
    alerts = await change
    assert len(alerts) == 1
    assert alerts[0] == test1.value

    now2 = datetime.datetime.now().replace(microsecond=0, tzinfo=datetime.UTC)
    test2 = RpcAlert.new(RpcAlert.WARNING_MIN, "Test2", now2)
    change = value_client.wait_for_change("test/device/.device/alerts")
    await device.change_alerts(add=test2, rem=test1)
    alerts = await change
    assert len(alerts) == 1
    assert alerts[0] == test2.value

    assert list(device.alerts) == [test2]


async def test_no_alerts(client, device):
    """Check that you alerts can't be accessed if they are disabled."""
    device.DEVICE_ALERTS = False
    assert await client.call("test/device/.device", "ls") == []
