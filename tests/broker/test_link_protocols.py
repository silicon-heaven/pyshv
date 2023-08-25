"""Check different transport protocols between broker and client."""
import asyncio
import dataclasses
import io
import logging
import os
import pty
import sys

import pytest

from shv import RpcProtocol, SimpleClient, broker

logger = logging.getLogger(__name__)


class Protocol:
    """Generic tests based on the protocol."""

    @pytest.fixture(name="broker_url")
    async def fixture_broker_url(self, url):
        return url

    @pytest.fixture(name="shvbroker")
    async def fixture_shvbroker(self, event_loop, config, broker_url):
        config.listen = {"test": broker_url}
        b = broker.RpcBroker(config)
        await b.start_serving()
        yield b
        await b.terminate()

    async def test_with_client(self, shvbroker, url):
        client = await SimpleClient.connect(url)
        assert "foo" == await client.call("", "echo", "foo")
        await client.disconnect()


class TestProtocolTCP(Protocol):
    """Check that we can work over TCP/IP transport protocol."""


class TestProtocolUnix(Protocol):
    """Check that we can work over Unix (local socket) transport protocol."""

    @pytest.fixture(name="url")
    def fixture_url(self, url, tmp_path):
        return dataclasses.replace(
            url,
            protocol=RpcProtocol.LOCAL_SOCKET,
            location=str(tmp_path / "broker.sock"),
        )


class TestProtocolUDP(Protocol):
    """Check that we can work over UDP/IP transport protocol."""

    @pytest.fixture(name="url")
    def fixture_url(self, url):
        return dataclasses.replace(url, protocol=RpcProtocol.UDP)
