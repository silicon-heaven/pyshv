"""Check implementation of SimpleDevice."""

import datetime

import pytest

from shv import (
    SHV_VERSION_MAJOR,
    SHV_VERSION_MINOR,
    VERSION,
    RpcMethodAccess,
    RpcMethodDesc,
    RpcMethodNotFoundError,
    SimpleDevice,
    shvmeta_eq,
)


class Device(SimpleDevice):
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
        ("test/device/.app/device", "name", "testdev"),
        ("test/device/.app/device", "version", "0.0.x"),
        ("test/device/.app/device", "serialNumber", None),
    ),
)
async def test_call(client, device, path, method, result):
    """Check that we can call various methods using blocking call."""
    res = await client.call(path, method)
    assert shvmeta_eq(res, result)


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
        ("test/device", [".app"]),
        ("test/device/.app", ["device"]),
        ("test/device/.app/device", []),
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
            "test/device/.app/device",
            [
                RpcMethodDesc.stddir(),
                RpcMethodDesc.stdls(),
                RpcMethodDesc.stdlsmod(),
                RpcMethodDesc.getter(
                    "name", "Null", "String", access=RpcMethodAccess.BROWSE
                ),
                RpcMethodDesc.getter(
                    "version", "Null", "String", access=RpcMethodAccess.BROWSE
                ),
                RpcMethodDesc.getter(
                    "serialNumber",
                    "Null",
                    "OptionalString",
                    access=RpcMethodAccess.BROWSE,
                ),
            ],
        ),
    ),
)
async def test_dir(client, device, path, result):
    """Verify that we can use dir method."""
    res = await client.dir(path)
    assert res == result
