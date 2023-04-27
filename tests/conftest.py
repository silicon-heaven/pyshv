import asyncio
import pathlib
import socket
import subprocess
import time

import pytest

from shv import RpcClient


@pytest.fixture(name="port", scope="module")
def fixture_port(unused_tcp_port_factory):
    """Override for port for shvbroker."""
    return unused_tcp_port_factory()


@pytest.fixture(name="sslport", scope="module")
def fixture_sslport(unused_tcp_port_factory):
    """Override for sslPort for shvbroker."""
    return unused_tcp_port_factory()


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
async def fixture_client(shvbroker, port):
    client = await RpcClient.connect(host="localhost", port=port)
    await client.login(
        user="admin",
        password="admin!123",
        login_type=RpcClient.LoginType.PLAIN,
    )
    yield client
    await client.disconnect()
