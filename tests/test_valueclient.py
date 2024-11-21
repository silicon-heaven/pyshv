"""Test ValueClient specific tools."""

import asyncio

import pytest


async def test_prop_cache(value_client, example_device):
    """Check that we correctly cache values in value client."""
    await value_client.subscribe("test/device/track/**:*:*")
    assert len(value_client) == 0
    assert not list(iter(value_client))
    assert "test/device/track/1" not in value_client
    assert await value_client.prop_get("test/device/track/1", 8) == [0]
    assert len(value_client) == 1
    assert value_client["test/device/track/1"] == [0]
    assert await value_client.prop_get("test/device/track/1", 8) == [0]
    await value_client.prop_set("test/device/track/1", [1, 2])
    assert value_client["test/device/track/1"] == [1, 2]
    await value_client.unsubscribe("test/device/track/**:*:*")
    assert len(value_client) == 0


async def test_unsubscribe_keep_cache(value_client, example_device):
    """Check that unsubscribe can keep the cached values."""
    await value_client.subscribe("test/device/**:*:*")
    await value_client.prop_get("test/device/track/1")
    assert "test/device/track/1" in value_client
    await value_client.unsubscribe("test/device/**:*:*", clean_cache=False)
    assert "test/device/track/1" in value_client


async def test_is_subscribed(value_client, example_device):
    """Check that we correctly trak our own subscriptions."""
    assert not value_client.is_subscribed("test/foo")
    await value_client.subscribe("test/**:*:*")
    assert value_client.is_subscribed("test/foo")
    assert value_client.is_subscribed("test/device")
    assert value_client.is_subscribed("test/device/any/other/path/under")
    assert not value_client.is_subscribed(".broker")
    assert not value_client.is_subscribed("tester")  # A different node
    await value_client.unsubscribe("test/**:*:*")
    assert not value_client.is_subscribed("test")


async def test_get_snapshot(value_client, example_device):
    """Check ability of get_snapshot to cache required properties."""
    await value_client.subscribe("test/**:*:*")
    await value_client.get_snapshot("test/device")
    assert "test/device/track/1" in value_client


async def test_get_snapshot_subscribes(value_client, example_device):
    """Check get_snapshot without arguments."""
    await value_client.subscribe("test/device/track/*:*:*")
    await value_client.get_snapshot()
    assert "test/device/track/1" in value_client
    assert len(value_client) == 8


async def test_get_snapshot_lower_subscribe(value_client, example_device):
    """Check that get_snapshot caches only subscribed paths."""
    await value_client.subscribe("test/device/track/2:*:*")
    await value_client.get_snapshot("test")
    assert len(value_client) == 1
    assert "test/device/track/2" in value_client


async def test_wait_for_change(value_client, example_device):
    """Check that simple wait for change notification works."""
    await value_client.subscribe("test/device/**:*:*")
    task1 = asyncio.create_task(value_client.wait_for_change("test/device/track/1"))
    task2 = asyncio.create_task(value_client.wait_for_change("test/device/track/1"))
    await value_client.prop_set("test/device/track/1", [1, 3])
    assert await task1 == [1, 3]
    assert await task2 == [1, 3]


@pytest.mark.parametrize("path", ("test/device", "test", ""))
async def test_prop_change(value_client, example_device, path):
    """Check hook for property change."""
    res = []

    def hook(client, path, value):
        res.append((client, path, value))

    await value_client.subscribe("test/device/**:*:*")
    value_client.on_change(path, hook)
    await value_client.prop_set("test/device/track/1", [1, 2])
    await value_client.prop_set("test/device/track/4", [])
    value_client.on_change(path, None)
    await value_client.prop_set("test/device/track/3", [])

    assert res == [
        (value_client, "test/device/track/1", [1, 2]),
        (value_client, "test/device/track/4", []),
    ]


async def test_prop_change_wait(value_client, example_device):
    """Check that we can wait for property change with prop_change_wait."""
    task1 = asyncio.create_task(value_client.prop_change_wait("test/device/track/1"))
    task2 = asyncio.create_task(value_client.prop_change_wait("test/device/track/1"))
    await value_client.prop_set("test/device/track/1", [1, 3])
    assert await task1 == [1, 3]
    assert await task2 == [1, 3]


async def test_prop_change_subscribed(value_client, example_device):
    """Check that we can wait for property change with prop_change_wait."""
    await value_client.subscribe("test/device/**:*:*")
    task1 = asyncio.create_task(value_client.prop_change_wait("test/device/track/1"))
    task2 = asyncio.create_task(value_client.prop_change_wait("test/device/track/1"))
    await value_client.prop_set("test/device/track/1", [1, 3])
    assert await task1 == [1, 3]
    assert await task2 == [1, 3]


async def test_prop_change_timeout(value_client, example_device):
    """Check that we can will timeout from prop_change_wait."""
    await value_client.subscribe("test/device/**:*:*")
    await value_client.prop_get("test/device/track/1")  # seed cache
    with pytest.raises(TimeoutError):
        print(
            await value_client.prop_change_wait(
                "test/device/track/1", get_period=0.2, timeout=1
            )
        )
