import asyncio
import pathlib
import socket
import subprocess
import time
import dataclasses

import pytest

from shv import RpcLoginType, RpcUrl, SimpleClient
from example_device import example_device


@pytest.fixture(name="port", scope="module")
def fixture_port(unused_tcp_port_factory):
    """Override for port for shvbroker."""
    return unused_tcp_port_factory()


@pytest.fixture(name="sslport", scope="module")
def fixture_sslport(unused_tcp_port_factory):
    """Override for sslPort for shvbroker."""
    return unused_tcp_port_factory()


@pytest.fixture(name="url", scope="module")
def fixture_url(port):
    """Provides RpcUrl for connecting to the broker."""
    return RpcUrl(
        host="localhost",
        port=port,
        username="admin",
        password="admin!123",
        login_type=RpcLoginType.PLAIN,
    )


@pytest.fixture(name="shvbroker", scope="module")
def fixture_shvbroker(port, sslport):
    """SHV broker usable for all tests."""
    confdir = pathlib.Path(__file__).parent / "shvbroker-etc"
    with subprocess.Popen(
        [
            "shvbroker",
            "--config-dir",
            str(confdir),
            "--server-port",
            str(port),
            "--server-ssl-port",
            str(sslport),
        ]
    ) as proc:
        while True:
            try:
                with socket.create_connection(("localhost", port)):
                    break
            except OSError:
                time.sleep(0.01)
        yield
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise


@pytest.fixture(name="client")
async def fixture_client(shvbroker, url):
    client = await SimpleClient.connect(url)
    yield client
    await client.disconnect()


@pytest.fixture(name="example_device")
async def fixture_example_device(event_loop, shvbroker, url):
    """Run example device and provide socket to access it."""
    nurl = dataclasses.replace(url, device_mount_point="test/device")
    task = event_loop.create_task(example_device(nurl))
    yield task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
