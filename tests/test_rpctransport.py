"""Check various clients and servers implementing a different link layers."""

from __future__ import annotations

import asyncio
import collections.abc
import contextlib
import dataclasses
import io
import logging
import os
import pty
import select
import threading

import pytest

from shv import (
    RpcClient,
    RpcClientPipe,
    RpcClientTCP,
    RpcClientTTY,
    RpcClientUnix,
    RpcClientWebSockets,
    RpcMessage,
    RpcServerTCP,
    RpcServerTTY,
    RpcServerUnix,
    RpcServerWebSockets,
    RpcServerWebSocketsUnix,
)

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class PTYPort:
    """PTY based exchange port."""

    port1: str
    port2: str
    event: threading.Event

    @classmethod
    @contextlib.contextmanager
    def new(cls) -> collections.abc.Iterator[PTYPort]:
        """Context function that provides PTY based ports.

        :return: Tuple with two strings containing paths to the pty ports and
          event that can be cleared to pause data exchange and set to resume it
          again.
        """
        pty1_master, pty1_slave = pty.openpty()
        pty2_master, pty2_slave = pty.openpty()
        event = threading.Event()
        event.set()
        thread = threading.Thread(
            target=cls._exchange, args=(pty1_master, pty2_master, event)
        )
        thread.start()
        yield cls(os.ttyname(pty1_slave), os.ttyname(pty2_slave), event)
        os.close(pty1_slave)
        os.close(pty2_slave)
        thread.join()

    @staticmethod
    def _exchange(fd1: int, fd2: int, event: threading.Event) -> None:
        p = select.poll()
        p.register(fd1, select.POLLIN | select.POLLPRI)
        p.register(fd2, select.POLLIN | select.POLLPRI)
        fds = 2
        while fds:
            for fd, pevent in p.poll():
                event.wait()
                if pevent & select.POLLHUP:
                    p.unregister(fd)
                    fds -= 1
                if pevent & select.POLLIN:
                    data = os.read(fd, io.DEFAULT_BUFFER_SIZE)
                    os.write(fd1 if fd is fd2 else fd2, data)
                if pevent & select.POLLERR:
                    logger.error("Error detected in ptycopy")
                    return


@pytest.fixture(name="pty")
def fixture_pty():
    with PTYPort.new() as port:
        yield port


class Link:
    """Generic tests applied to link layers."""

    async def test_msg_a(self, clients):
        msg = RpcMessage.request(".app", "dir")
        await clients[0].send(msg)
        assert await clients[1].receive() == msg

    async def test_msg_b(self, clients):
        msg = RpcMessage.signal(".app")
        await clients[1].send(msg)
        assert await clients[0].receive() == msg

    @pytest.mark.parametrize("a,b", ((0, 1), (1, 0)))
    async def test_reset(self, clients, a, b):
        await clients[a].reset()
        assert await clients[b].receive() == RpcClient.Control.RESET


class ServerLink(Link):
    """Additional tests for server-client connections."""

    @pytest.mark.parametrize("cdisc,crecv", ((0, 1), (1, 0)))
    async def test_eof_receive(self, clients, cdisc, crecv):
        clients[cdisc].disconnect()
        await clients[cdisc].wait_disconnect()
        assert not clients[cdisc].connected
        with pytest.raises(EOFError):
            await clients[crecv].receive()
        assert not clients[crecv].connected

    @pytest.mark.parametrize("cdisc,crecv", ((0, 1), (1, 0)))
    async def test_eof_send(self, clients, cdisc, crecv):
        clients[cdisc].disconnect()
        await clients[cdisc].wait_disconnect()
        with pytest.raises(EOFError):
            await clients[crecv].send(RpcMessage.request(".app", "ping"))
        assert not clients[crecv].connected

    async def test_reconnect(self, clients, server):
        clients[1].disconnect()
        await clients[1].wait_disconnect()
        await clients[1].reset()
        server_client = await server[1].get()
        msg = RpcMessage.request("foo", "ls")
        await clients[1].send(msg)
        assert await server_client.receive() == msg
        server_client.disconnect()
        await server_client.wait_disconnect()


class TestPipe(Link):
    """Check that we can work over Unix pipe pair."""

    @pytest.fixture(name="clients")
    async def fixture_clients(self):
        client1, client2 = await RpcClientPipe.open_pair()
        yield client1, client2
        client1.disconnect()
        client2.disconnect()
        await client1.wait_disconnect()
        await client2.wait_disconnect()


class TestTCP(ServerLink):
    """Check that TCP/IP transport protocol works."""

    @pytest.fixture(name="server")
    async def fixture_server(self, port):
        queue = asyncio.Queue()
        server = RpcServerTCP(queue.put, "localhost", port)
        await server.listen()
        yield server, queue
        server.close()
        await server.wait_closed()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, port):
        client = await RpcClientTCP.connect("localhost", port)
        server_client = await server[1].get()
        yield server_client, client
        client.disconnect()
        server_client.disconnect()
        await client.wait_disconnect()
        await server_client.wait_disconnect()

    async def test_before_connect(self, port) -> None:
        client = RpcClientTCP("localhost", port)
        with pytest.raises(EOFError):
            await client.receive()
        with pytest.raises(EOFError):
            await client.send(RpcMessage.request(".app", "ping"))
        client.disconnect()
        await client.wait_disconnect()


class TestUnix(ServerLink):
    """Check that Unix transport protocol works."""

    @pytest.fixture(name="sockpath")
    def fixture_sockpath(self, tmp_path):
        return tmp_path / "s"

    @pytest.fixture(name="server")
    async def fixture_server(self, sockpath):
        queue = asyncio.Queue()
        server = RpcServerUnix(queue.put, sockpath)
        await server.listen()
        yield server, queue
        server.close()
        await server.wait_closed()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, sockpath):
        client = await RpcClientUnix.connect(sockpath)
        server_client = await server[1].get()
        yield server_client, client
        server_client.disconnect()
        client.disconnect()
        await server_client.wait_disconnect()
        await client.wait_disconnect()


class TestTTY(Link):
    """Check that we can work over TTY port transport protocol."""

    @pytest.fixture(name="clients")
    async def fixture_clients(self, pty):
        # We pause data exchange to resolve race condition between terminal
        # setup and reset message sending. This ensures that ports are
        # configured to raw mode before reset message is exchanged.
        pty.event.clear()
        client1 = await RpcClientTTY.connect(pty.port1)
        client2 = await RpcClientTTY.connect(pty.port2)
        pty.event.set()

        # Flush reset sent by clients
        assert await client1.receive() is RpcClient.Control.RESET
        assert await client2.receive() is RpcClient.Control.RESET

        yield client1, client2

        client1.disconnect()
        client2.disconnect()
        await client1.wait_disconnect()
        await client2.wait_disconnect()

    async def test_escapes(self, clients):
        msg = RpcMessage.request("prop", "set", b"1\xa2\xa3\xa4\xa5\xaa2")
        await clients[0].send(msg)
        assert await clients[1].receive() == msg


class TestTTYServer(Link):
    """Check that we can work over TTY port transport protocol and its server."""

    @pytest.fixture(name="server")
    async def fixture_server(self, pty):
        pty.event.clear()
        queue = asyncio.Queue()
        server = RpcServerTTY(queue.put, pty.port1)
        await server.listen()
        yield server, queue
        server.terminate()
        await server.wait_terminated()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, pty):
        client = await RpcClientTTY.connect(pty.port2)
        server_client = await server[1].get()
        pty.event.set()
        assert await server_client.receive() is RpcClient.Control.RESET
        assert await client.receive() is RpcClient.Control.RESET
        yield server_client, client
        client.disconnect()
        server_client.disconnect()
        await client.wait_disconnect()
        await server_client.wait_disconnect()


class TestWebSockets(ServerLink):
    """Check that WebSockets transport protocol works."""

    @pytest.fixture(name="server")
    async def fixture_server(self, port):
        queue = asyncio.Queue()
        server = RpcServerWebSockets(queue.put, "localhost", port)
        await server.listen()
        yield server, queue
        server.close()
        await server.wait_closed()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, port):
        client = await RpcClientWebSockets.connect("localhost", port)
        server_client = await server[1].get()
        await asyncio.sleep(0)
        yield server_client, client
        client.disconnect()
        server_client.disconnect()
        await client.wait_disconnect()
        await server_client.wait_disconnect()

    async def test_before_connect(self, port) -> None:
        client = RpcClientWebSockets("localhost", port)
        with pytest.raises(EOFError):
            await client.receive()
        with pytest.raises(EOFError):
            await client.send(RpcMessage.request(".app", "ping"))
        client.disconnect()
        await client.wait_disconnect()


class TestWebSocketsUnix(ServerLink):
    """Check that WebSockets Unix transport protocol works."""

    @pytest.fixture(name="sockpath")
    def fixture_sockpath(self, tmp_path):
        return tmp_path / "s"

    @pytest.fixture(name="server")
    async def fixture_server(self, sockpath):
        queue = asyncio.Queue()
        server = RpcServerWebSocketsUnix(queue.put, sockpath)
        await server.listen()
        yield server, queue
        server.close()
        await server.wait_closed()

    @pytest.fixture(name="clients")
    async def fixture_clients(self, server, sockpath):
        client = await RpcClientWebSockets.connect(sockpath)
        server_client = await server[1].get()
        yield server_client, client
        server_client.disconnect()
        client.disconnect()
        await server_client.wait_disconnect()
        await client.wait_disconnect()
