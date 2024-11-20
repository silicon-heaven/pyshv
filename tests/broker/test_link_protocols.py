"""Check different transport protocols between broker and client."""

import dataclasses
import logging

import pytest

from shv import RpcProtocol, SHVClient, broker

logger = logging.getLogger(__name__)


class Protocol:
    """Generic tests based on the protocol."""

    @pytest.fixture(name="broker_url")
    async def fixture_broker_url(self, url):
        return url

    @pytest.fixture(name="shvbroker")
    async def fixture_shvbroker(self, config, broker_url):
        config.listen = [broker_url]
        b = broker.RpcBroker(config)
        await b.start_serving()
        yield b
        await b.terminate()

    async def test_with_client(self, shvbroker, url):
        client = await SHVClient.connect(url)
        assert await client.call(".app", "ping") is None
        await client.disconnect()


class TestProtocolTCP(Protocol):
    """Check that we can work over TCP/IP transport protocol."""


class TestProtocolUnix(Protocol):
    """Check that we can work over Unix (local socket) transport protocol."""

    @pytest.fixture(name="url")
    def fixture_url(self, url, tmp_path):
        return dataclasses.replace(
            url,
            protocol=RpcProtocol.UNIX,
            location=str(tmp_path / "broker.sock"),
        )
